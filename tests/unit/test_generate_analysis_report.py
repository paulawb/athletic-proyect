from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.application.use_cases.generate_analysis_report import GenerateAnalysisReport
from app.core.exceptions import AnalysisNotFoundError, MetricsNotFoundError
from app.domain.entities.analysis import Analysis, AnalysisStatus
from app.domain.entities.athlete import Athlete
from app.domain.entities.frame_metrics import FrameMetrics
from app.domain.entities.metrics import Metrics
from app.domain.entities.test import Test
from app.domain.entities.video import Video, VideoStatus
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.athlete_repository import AthleteRepository
from app.domain.repositories.metrics_repository import FrameMetricsRepository, MetricsRepository
from app.domain.repositories.test_repository import TestRepository
from app.domain.repositories.video_repository import VideoRepository
from app.domain.services.report_generator import AnalysisReportData, ReportGenerator


class FakeAnalysisRepository(AnalysisRepository):
    def __init__(self, analyses: list[Analysis] | None = None) -> None:
        self._analyses = {a.id: a for a in (analyses or [])}

    async def create(self, analysis: Analysis) -> Analysis:
        self._analyses[analysis.id] = analysis
        return analysis

    async def get_by_id(self, analysis_id: int) -> Analysis | None:
        return self._analyses.get(analysis_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Analysis]:
        return list(self._analyses.values())[skip : skip + limit]

    async def list_by_video_id(self, video_id: int) -> list[Analysis]:
        return [a for a in self._analyses.values() if a.video_id == video_id]

    async def update_progress(self, analysis_id, status, processed_frames, error_message=None) -> Analysis:
        raise NotImplementedError("no se usa en estas pruebas")

    async def update_progress_batch(self, analysis_id: int, processed_frames: int) -> None:
        raise NotImplementedError("no se usa en estas pruebas")


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
        raise NotImplementedError("no se usa en estas pruebas")


class FakeAthleteRepository(AthleteRepository):
    def __init__(self, athletes: list[Athlete] | None = None) -> None:
        self._athletes = {a.id: a for a in (athletes or [])}

    async def create(self, athlete: Athlete) -> Athlete:
        self._athletes[athlete.id] = athlete
        return athlete

    async def get_by_id(self, athlete_id: int) -> Athlete | None:
        return self._athletes.get(athlete_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Athlete]:
        return list(self._athletes.values())[skip : skip + limit]

    async def update(self, athlete: Athlete) -> Athlete:
        raise NotImplementedError("no se usa en estas pruebas")


class FakeMetricsRepository(MetricsRepository):
    def __init__(self, metrics: list[Metrics] | None = None) -> None:
        self._metrics = metrics or []

    async def create(self, metrics: Metrics) -> Metrics:
        self._metrics.append(metrics)
        return metrics

    async def get_by_analysis_id(self, analysis_id: int) -> Metrics | None:
        return next((m for m in self._metrics if m.analysis_id == analysis_id), None)


class FakeFrameMetricsRepository(FrameMetricsRepository):
    def __init__(self, frame_metrics: list[FrameMetrics] | None = None) -> None:
        self._frame_metrics = frame_metrics or []

    async def bulk_create(self, frame_metrics: list[FrameMetrics]) -> None:
        self._frame_metrics.extend(frame_metrics)

    async def list_by_analysis_id(self, analysis_id: int) -> list[FrameMetrics]:
        return [fm for fm in self._frame_metrics if fm.analysis_id == analysis_id]


class FakeReportGenerator(ReportGenerator):
    """No genera un PDF real (eso lo prueba el propio PdfReportGenerator, no
    unit-testeable sin las dependencias instaladas): solo confirma que
    GenerateAnalysisReport le arma los datos correctos."""

    def __init__(self) -> None:
        self.received: AnalysisReportData | None = None

    def generate(self, report_data: AnalysisReportData) -> bytes:
        self.received = report_data
        return b"%PDF-fake"


def _now(days_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _athlete() -> Athlete:
    return Athlete(id=1, first_name="Juan", last_name="Pérez", identification="100123456", age=17, gender="M")


def _build_scenario():
    """Un atleta con dos pruebas: la actual (id=2) y una anterior completada
    (id=1) que sirve de punto de comparacion."""
    athlete = _athlete()

    previous_test = Test(
        id=1, athlete_id=1, distance=10, test_type="Carrera de velocidad", technique="Salida de tacos",
        created_at=_now(days_ago=7),
    )
    current_test = Test(
        id=2, athlete_id=1, distance=10, test_type="Carrera de velocidad", technique="Salida de tacos",
        created_at=_now(),
    )

    previous_video = Video(
        id=1, test_id=1, original_filename="carrera_anterior.mp4", storage_path="videos/1.mp4",
        file_size=1024, width=1920, status=VideoStatus.VALIDATED,
    )
    current_video = Video(
        id=2, test_id=2, original_filename="carrera_actual.mp4", storage_path="videos/2.mp4",
        file_size=1024, width=1920, status=VideoStatus.VALIDATED,
    )

    previous_analysis = Analysis(
        id=1, video_id=1, status=AnalysisStatus.COMPLETED, processed_frames=45, total_frames=45,
        completed_at=_now(days_ago=7),
    )
    current_analysis = Analysis(
        id=2, video_id=2, status=AnalysisStatus.COMPLETED, processed_frames=45, total_frames=45,
        completed_at=_now(),
    )

    previous_metrics = Metrics(
        analysis_id=1, average_speed=6.5, maximum_speed=7.2, stride_length=1.7, cadence=4.0, posture_score=80.0
    )
    current_metrics = Metrics(
        analysis_id=2, average_speed=7.2, maximum_speed=8.1, stride_length=1.9, cadence=4.3, posture_score=88.0
    )

    return {
        "athlete_repository": FakeAthleteRepository([athlete]),
        "test_repository": FakeTestRepository([previous_test, current_test]),
        "video_repository": FakeVideoRepository([previous_video, current_video]),
        "analysis_repository": FakeAnalysisRepository([previous_analysis, current_analysis]),
        "metrics_repository": FakeMetricsRepository([previous_metrics, current_metrics]),
        "frame_metrics_repository": FakeFrameMetricsRepository(
            [
                FrameMetrics(
                    analysis_id=2, frame_number=i, timestamp=i / 30, x_position=float(i), y_position=0.0,
                    speed=2.0, stride_phase="vuelo", posture_score=88.0,
                )
                for i in range(5)
            ]
        ),
    }


async def test_generate_report_assembles_athlete_test_and_metrics() -> None:
    scenario = _build_scenario()
    report_generator = FakeReportGenerator()
    use_case = GenerateAnalysisReport(report_generator=report_generator, **scenario)

    await use_case.execute(analysis_id=2)

    assert report_generator.received is not None
    data = report_generator.received
    assert data.athlete_full_name == "Juan Pérez"
    assert data.athlete_identification == "100123456"
    assert data.metrics.average_speed == 7.2
    assert len(data.frame_metrics) == 5


async def test_generate_report_includes_previous_completed_test_as_comparison() -> None:
    scenario = _build_scenario()
    report_generator = FakeReportGenerator()
    use_case = GenerateAnalysisReport(report_generator=report_generator, **scenario)

    await use_case.execute(analysis_id=2)

    comparison = report_generator.received.previous_tests
    assert len(comparison) == 1
    assert comparison[0].average_speed == 6.5
    assert comparison[0].test_label == "Prueba #1"


async def test_generate_report_returns_bytes_from_report_generator() -> None:
    scenario = _build_scenario()
    use_case = GenerateAnalysisReport(report_generator=FakeReportGenerator(), **scenario)

    result = await use_case.execute(analysis_id=2)

    assert result == b"%PDF-fake"


async def test_generate_report_raises_when_analysis_does_not_exist() -> None:
    scenario = _build_scenario()
    use_case = GenerateAnalysisReport(report_generator=FakeReportGenerator(), **scenario)

    with pytest.raises(AnalysisNotFoundError):
        await use_case.execute(analysis_id=999)


async def test_generate_report_raises_when_metrics_not_yet_available() -> None:
    scenario = _build_scenario()
    scenario["metrics_repository"] = FakeMetricsRepository([])  # sin metricas persistidas
    use_case = GenerateAnalysisReport(report_generator=FakeReportGenerator(), **scenario)

    with pytest.raises(MetricsNotFoundError):
        await use_case.execute(analysis_id=2)


async def test_generate_report_has_no_comparison_when_athlete_has_no_previous_tests() -> None:
    scenario = _build_scenario()
    # Solo la prueba actual: sin pruebas anteriores para comparar.
    scenario["test_repository"] = FakeTestRepository(
        [t for t in scenario["test_repository"]._tests.values() if t.id == 2]
    )
    fake_generator = FakeReportGenerator()
    use_case = GenerateAnalysisReport(report_generator=fake_generator, **scenario)

    await use_case.execute(analysis_id=2)

    assert fake_generator.received.previous_tests == []
