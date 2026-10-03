from __future__ import annotations

import pytest

from app.application.use_cases.get_analysis import GetAnalysis
from app.application.use_cases.process_video_frames import ProcessVideoFrames
from app.core.exceptions import AnalysisNotFoundError
from app.domain.entities.analysis import Analysis, AnalysisStatus
from app.domain.entities.frame_metrics import FrameMetrics
from app.domain.entities.metrics import Metrics
from app.domain.entities.test import Test
from app.domain.entities.video import Video, VideoStatus
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.metrics_repository import FrameMetricsRepository, MetricsRepository
from app.domain.repositories.test_repository import TestRepository
from app.domain.repositories.video_repository import VideoRepository
from app.domain.services.frame_processor import FrameProcessor
from app.domain.services.metrics_calculator import (
    CameraCalibration,
    CoordinateCalibrator,
    FrameMetricValue,
    MetricsCalculator,
    MetricsResult,
)
from app.domain.services.pose_estimator import Keypoint, PoseEstimationResult, PoseEstimator
from app.domain.services.video_storage import VideoStorage
from app.infrastructure.calibration.linear_coordinate_calibrator import LinearCoordinateCalibrator


class FakeVideoRepository(VideoRepository):
    def __init__(self, videos: list[Video] | None = None) -> None:
        self._videos = {v.id: v for v in (videos or [])}

    async def create(self, video: Video) -> Video:
        self._videos[video.id] = video
        return video

    async def get_by_id(self, video_id: int) -> Video | None:
        return self._videos.get(video_id)

    async def get_by_test_id(self, test_id: int) -> Video | None:
        matches = [v for v in self._videos.values() if v.test_id == test_id]
        return matches[-1] if matches else None


class FakeTestRepository(TestRepository):
    def __init__(self, tests: list[Test] | None = None) -> None:
        self._tests = {t.id: t for t in (tests or [])}

    async def create(self, test: Test) -> Test:
        self._tests[test.id] = test
        return test

    async def get_by_id(self, test_id: int) -> Test | None:
        return self._tests.get(test_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Test]:
        return list(self._tests.values())[skip : skip + limit]

    async def list_by_athlete(self, athlete_id: int) -> list[Test]:
        return [t for t in self._tests.values() if t.athlete_id == athlete_id]

    async def update_status(self, test_id: int, status: str) -> Test:
        test = self._tests[test_id]
        test.status = status
        return test


class FakeAnalysisRepository(AnalysisRepository):
    def __init__(self) -> None:
        self._analyses: dict[int, Analysis] = {}
        self._next_id = 1

    async def create(self, analysis: Analysis) -> Analysis:
        analysis.id = self._next_id
        self._analyses[analysis.id] = analysis
        self._next_id += 1
        return analysis

    async def get_by_id(self, analysis_id: int) -> Analysis | None:
        return self._analyses.get(analysis_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Analysis]:
        return list(self._analyses.values())[skip : skip + limit]

    async def list_by_video_id(self, video_id: int) -> list[Analysis]:
        return [a for a in self._analyses.values() if a.video_id == video_id]

    async def update_progress(
        self,
        analysis_id: int,
        status: AnalysisStatus,
        processed_frames: int,
        error_message: str | None = None,
    ) -> Analysis:
        analysis = self._analyses[analysis_id]
        analysis.status = status
        analysis.processed_frames = processed_frames
        if error_message is not None:
            analysis.error_message = error_message
        return analysis

    async def update_progress_batch(self, analysis_id: int, processed_frames: int) -> None:
        """Actualización liviana: solo processed_frames, sin SELECT ni RETURNING."""
        if analysis_id in self._analyses:
            self._analyses[analysis_id].processed_frames = processed_frames


class FakeMetricsRepository(MetricsRepository):
    def __init__(self) -> None:
        self.created: list[Metrics] = []

    async def create(self, metrics: Metrics) -> Metrics:
        metrics.id = len(self.created) + 1
        self.created.append(metrics)
        return metrics

    async def get_by_analysis_id(self, analysis_id: int) -> Metrics | None:
        return next((m for m in self.created if m.analysis_id == analysis_id), None)


class FakeFrameMetricsRepository(FrameMetricsRepository):
    def __init__(self) -> None:
        self.bulk_create_calls: list[list[FrameMetrics]] = []

    async def bulk_create(self, frame_metrics: list[FrameMetrics]) -> None:
        self.bulk_create_calls.append(frame_metrics)

    async def list_by_analysis_id(self, analysis_id: int) -> list[FrameMetrics]:
        for batch in self.bulk_create_calls:
            if batch and batch[0].analysis_id == analysis_id:
                return batch
        return []


class FakeVideoStorage(VideoStorage):
    """Solo se usa get_absolute_path en este caso de uso; el resto no aplica."""

    def get_absolute_path(self, storage_path: str) -> str:
        return f"/fake/{storage_path}"

    async def save(self, file, destination_id, max_size_bytes=None):
        raise NotImplementedError("no se usa en estas pruebas")

    async def delete(self, storage_path: str) -> None:
        raise NotImplementedError("no se usa en estas pruebas")


class FakeFrameProcessor(FrameProcessor):
    """Simula el recorrido cuadro por cuadro sin necesitar cv2 ni numpy real:
    el 'frame' es un objeto cualquiera, ya que ProcessVideoFrames solo
    verifica que no sea None."""

    def __init__(self, frame_count: int, fail_at_frame: int | None = None, fps: float = 30.0) -> None:
        self._frame_count = frame_count
        self._fail_at_frame = fail_at_frame
        self._fps = fps

    def iterate_frames(self, video_path: str):
        for i in range(self._frame_count):
            if self._fail_at_frame is not None and i == self._fail_at_frame:
                raise RuntimeError(f"fallo simulado leyendo el cuadro {i}")
            yield i, object(), i / self._fps

    def get_video_metadata(self, video_path: str):
        raise NotImplementedError("no se usa en estas pruebas")


class FakePoseEstimator(PoseEstimator):
    """Cuenta cuantas veces se le pidio estimar una pose, para verificar
    que ProcessVideoFrames la llama una vez por cada cuadro procesado."""

    def __init__(self, detect_pose: bool = True) -> None:
        self.calls: list[int] = []
        self.timestamps_ms: list[int | None] = []
        self._detect_pose = detect_pose

    def estimate(
        self, frame, frame_number: int, timestamp_ms: int | None = None
    ) -> PoseEstimationResult:
        self.calls.append(frame_number)
        self.timestamps_ms.append(timestamp_ms)
        return PoseEstimationResult(
            frame_number=frame_number,
            keypoints=(
                [Keypoint(name="nose", x=1.0, y=2.0, confidence=0.9)] if self._detect_pose else []
            ),
        )


class FakeMetricsCalculator(MetricsCalculator):
    """No verifica formulas (eso lo hace test_basic_metrics_calculator.py y
    test_biomechanical_metrics_calculator.py): solo confirma que
    ProcessVideoFrames se lo pide con los datos correctos y que persiste lo
    que este calculador devuelve."""

    def __init__(self) -> None:
        self.received_pose_results: list[PoseEstimationResult] | None = None
        self.received_calibrator: CoordinateCalibrator | None = None

    def calculate(self, pose_results, calibrator) -> MetricsResult:
        self.received_pose_results = pose_results
        self.received_calibrator = calibrator
        return MetricsResult(
            average_speed=7.5, maximum_speed=8.4, stride_length=1.9, cadence=4.2, posture_score=88.0
        )

    def calculate_frame_metrics(self, pose_results, calibrator) -> list[FrameMetricValue]:
        return [
            FrameMetricValue(
                frame_number=r.frame_number,
                timestamp=r.timestamp,
                x_position=1.0,
                y_position=2.0,
                speed=3.0,
                stride_phase="vuelo",
                posture_score=90.0,
            )
            for r in pose_results
        ]


def _existing_video(total_frames: int = 45, width: int | None = 1920) -> Video:
    return Video(
        id=1,
        test_id=1,
        original_filename="carrera_01.mp4",
        storage_path="videos/test-1.mp4",
        file_size=1024,
        total_frames=total_frames,
        width=width,
        status=VideoStatus.VALIDATED,
    )


def _existing_test(distance: int = 10) -> Test:
    return Test(id=1, athlete_id=1, distance=distance, test_type="Carrera de velocidad", technique="Salida de tacos")


def _default_calibrator_factory(video: Video, reference_distance_m: float) -> CoordinateCalibrator:
    """Imita la fabrica real del router (Fase 10): escala lineal a partir
    del ancho del video, o ValueError si no se conoce -ProcessVideoFrames
    ya sabe convertir eso en 'se omite el calculo de metricas'."""
    if not video.width:
        raise ValueError("dimensiones del video desconocidas")
    pixels_per_meter = video.width / reference_distance_m
    return LinearCoordinateCalibrator(
        CameraCalibration(pixels_per_meter=pixels_per_meter, reference_distance_m=reference_distance_m)
    )


async def _create_pending_analysis(analysis_repository: AnalysisRepository, video_id: int = 1, total_frames: int = 45) -> int:
    """Fase 8: ProcessVideoFrames ya no crea el Analysis (eso es CreateAnalysis),
    asi que las pruebas deben crearlo primero, igual que hace el router."""
    analysis = await analysis_repository.create(Analysis(video_id=video_id, total_frames=total_frames))
    return analysis.id


def _build_use_case(
    video_repository=None,
    test_repository=None,
    analysis_repository=None,
    metrics_repository=None,
    frame_metrics_repository=None,
    frame_processor=None,
    pose_estimator=None,
    metrics_calculator=None,
    calibrator_factory=None,
) -> ProcessVideoFrames:
    return ProcessVideoFrames(
        video_repository=video_repository or FakeVideoRepository([_existing_video()]),
        test_repository=test_repository or FakeTestRepository([_existing_test()]),
        analysis_repository=analysis_repository or FakeAnalysisRepository(),
        metrics_repository=metrics_repository or FakeMetricsRepository(),
        frame_metrics_repository=frame_metrics_repository or FakeFrameMetricsRepository(),
        video_storage=FakeVideoStorage(),
        frame_processor=frame_processor or FakeFrameProcessor(frame_count=45),
        pose_estimator=pose_estimator or FakePoseEstimator(),
        metrics_calculator=metrics_calculator or FakeMetricsCalculator(),
        calibrator_factory=calibrator_factory or _default_calibrator_factory,
    )


async def test_process_video_frames_completes_and_counts_all_frames() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    use_case = _build_use_case(analysis_repository=analysis_repository)

    analysis = await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert analysis.status == AnalysisStatus.COMPLETED
    assert analysis.processed_frames == 45
    assert analysis.progress_percentage == 100


async def test_process_video_frames_estimates_pose_for_every_frame() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    pose_estimator = FakePoseEstimator()
    use_case = _build_use_case(analysis_repository=analysis_repository, pose_estimator=pose_estimator)

    await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert pose_estimator.calls == list(range(45))
    assert pose_estimator.timestamps_ms[:3] == [0, 33, 67]
    assert len(use_case.pose_results) == 45
    assert all(isinstance(r, PoseEstimationResult) for r in use_case.pose_results)


async def test_process_video_frames_fails_when_no_person_is_detected() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    metrics_repository = FakeMetricsRepository()
    use_case = _build_use_case(
        analysis_repository=analysis_repository,
        metrics_repository=metrics_repository,
        pose_estimator=FakePoseEstimator(detect_pose=False),
    )

    result = await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert result.status == AnalysisStatus.FAILED
    assert result.error_message is not None
    assert "No se detectó ninguna persona" in result.error_message
    assert metrics_repository.created == []


async def test_process_video_frames_calculates_metrics_with_timestamps_and_calibration() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    metrics_calculator = FakeMetricsCalculator()
    use_case = _build_use_case(
        analysis_repository=analysis_repository,
        video_repository=FakeVideoRepository([_existing_video(total_frames=45, width=1920)]),
        test_repository=FakeTestRepository([_existing_test(distance=10)]),
        frame_processor=FakeFrameProcessor(frame_count=45, fps=30.0),
        metrics_calculator=metrics_calculator,
    )

    analysis = await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert use_case.metrics_result is not None
    assert use_case.metrics_result.average_speed == 7.5  # viene del FakeMetricsCalculator
    assert analysis.status == AnalysisStatus.COMPLETED

    # ProcessVideoFrames debe pasarle el timestamp real (no 0.0 para todos)
    # y un calibrador derivado del ancho del video y la distancia de la
    # prueba (1920 px / 10 m = 192 px/m).
    assert metrics_calculator.received_pose_results is not None
    timestamps = [r.timestamp for r in metrics_calculator.received_pose_results]
    assert timestamps[-1] > timestamps[0]
    assert metrics_calculator.received_calibrator is not None
    assert metrics_calculator.received_calibrator.pixel_to_world(192.0, 0.0) == pytest.approx((1.0, 0.0))


async def test_process_video_frames_persists_metrics_and_frame_metrics() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    metrics_repository = FakeMetricsRepository()
    frame_metrics_repository = FakeFrameMetricsRepository()
    use_case = _build_use_case(
        analysis_repository=analysis_repository,
        metrics_repository=metrics_repository,
        frame_metrics_repository=frame_metrics_repository,
    )

    analysis = await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert len(metrics_repository.created) == 1
    persisted = metrics_repository.created[0]
    assert persisted.analysis_id == analysis.id
    assert persisted.average_speed == 7.5  # viene del FakeMetricsCalculator

    assert len(frame_metrics_repository.bulk_create_calls) == 1
    persisted_frames = frame_metrics_repository.bulk_create_calls[0]
    assert len(persisted_frames) == 45
    assert all(fm.analysis_id == analysis.id for fm in persisted_frames)
    assert {fm.frame_number for fm in persisted_frames} == set(range(45))


async def test_process_video_frames_skips_metrics_when_video_width_unknown() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    metrics_calculator = FakeMetricsCalculator()
    metrics_repository = FakeMetricsRepository()
    frame_metrics_repository = FakeFrameMetricsRepository()
    use_case = _build_use_case(
        analysis_repository=analysis_repository,
        video_repository=FakeVideoRepository([_existing_video(total_frames=45, width=None)]),
        metrics_calculator=metrics_calculator,
        metrics_repository=metrics_repository,
        frame_metrics_repository=frame_metrics_repository,
    )

    await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert use_case.metrics_result is None
    assert metrics_calculator.received_pose_results is None
    assert metrics_repository.created == []
    assert frame_metrics_repository.bulk_create_calls == []


async def test_process_video_frames_marks_failed_when_video_disappears() -> None:
    """CreateAnalysis ya valida que el video exista al crear el Analysis;
    esto cubre el caso raro donde de todos modos desaparecio para cuando
    corre el procesamiento en segundo plano (Fase 8)."""
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    use_case = _build_use_case(analysis_repository=analysis_repository, video_repository=FakeVideoRepository([]))

    analysis = await use_case.execute(analysis_id=analysis_id, video_id=99)

    assert analysis.status == AnalysisStatus.FAILED
    assert "video" in analysis.error_message.lower()


async def test_process_video_frames_marks_failed_on_read_error() -> None:
    analysis_repository = FakeAnalysisRepository()
    analysis_id = await _create_pending_analysis(analysis_repository)
    pose_estimator = FakePoseEstimator()
    metrics_repository = FakeMetricsRepository()
    use_case = _build_use_case(
        analysis_repository=analysis_repository,
        frame_processor=FakeFrameProcessor(frame_count=45, fail_at_frame=20),
        pose_estimator=pose_estimator,
        metrics_repository=metrics_repository,
    )

    analysis = await use_case.execute(analysis_id=analysis_id, video_id=1)

    assert analysis.status == AnalysisStatus.FAILED
    assert analysis.processed_frames == 20
    assert "cuadro 20" in analysis.error_message
    # Se estimo pose para los 20 cuadros que sí se pudieron leer, ni uno mas,
    # y no se calculan ni persisten metricas sobre un analisis fallido.
    assert len(pose_estimator.calls) == 20
    assert use_case.metrics_result is None
    assert metrics_repository.created == []


async def test_get_analysis_raises_when_not_found() -> None:
    with pytest.raises(AnalysisNotFoundError):
        await GetAnalysis(FakeAnalysisRepository()).execute(999)
