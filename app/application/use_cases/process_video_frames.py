import asyncio
import dataclasses
import logging
import math
from typing import Callable

from app.core.exceptions import VideoProcessingError
from app.domain.entities.analysis import Analysis, AnalysisStatus
from app.domain.entities.frame_metrics import FrameMetrics
from app.domain.entities.metrics import Metrics
from app.domain.entities.video import Video
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.metrics_repository import FrameMetricsRepository, MetricsRepository
from app.domain.repositories.test_repository import TestRepository
from app.domain.repositories.video_repository import VideoRepository
from app.domain.services.frame_processor import FrameProcessor
from app.domain.services.metrics_calculator import CoordinateCalibrator, MetricsCalculator, MetricsResult
from app.domain.services.pose_estimator import Keypoint, KeypointName, PoseEstimationResult, PoseEstimator
from app.domain.services.trajectory_calibration import (
    TRACKING_CAMERA_MIN_DISTANCE_M,
    calibrate_to_trajectory,
    run_duration_seconds,
    simulate_tracking_camera_progress,
)
from app.domain.services.video_storage import VideoStorage

logger = logging.getLogger(__name__)

_PROGRESS_UPDATE_EVERY = 10
_TARGET_ANALYSIS_FPS = 20
_MAX_PLAUSIBLE_SPEED_MS = 15.0
_MIN_VALID_HIP_FRAMES = 3
_MIN_POSE_COVERAGE = 0.2
_MIN_CADENCE_STEPS_PER_SECOND = 0.5
# Short acceleration trials should not silently report a six-step estimate for
# 10 m (1.67 m/step). Reject low-coverage or inconsistent foot-strike estimates
# rather than publishing a misleading step length.
_MAX_SHORT_TRIAL_STEP_LENGTH_M = 1.6
_MAX_SHORT_TRIAL_DISTANCE_M = 20.0


def _analysis_frame_step(fps: float | None) -> int:
    if not fps or fps <= 0:
        return 1
    return max(1, int(fps // _TARGET_ANALYSIS_FPS))


_ITERATOR_EXHAUSTED = object()
CalibratorFactory = Callable[[Video, float], CoordinateCalibrator]


def _advance_iterator(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return _ITERATOR_EXHAUSTED


def _has_valid_hips(result: PoseEstimationResult) -> bool:
    by_name = {point.name: point for point in result.keypoints}
    left = by_name.get(KeypointName.LEFT_HIP.value)
    right = by_name.get(KeypointName.RIGHT_HIP.value)
    return bool(
        left
        and right
        and math.isfinite(left.x)
        and math.isfinite(left.y)
        and math.isfinite(right.x)
        and math.isfinite(right.y)
        and left.confidence >= 0.35
        and right.confidence >= 0.35
    )


def _distance_per_detected_step(distance_m: float, step_count: int | None) -> float:
    if not math.isfinite(distance_m) or distance_m <= 0 or step_count is None or step_count <= 0:
        raise VideoProcessingError("No se pudo determinar una cantidad válida de pasos detectados.")
    step_length = distance_m / step_count
    if distance_m <= _MAX_SHORT_TRIAL_DISTANCE_M and step_length > _MAX_SHORT_TRIAL_STEP_LENGTH_M:
        raise VideoProcessingError(
            f"Solo se detectaron {step_count} pasos para {distance_m:g} m (promedio {step_length:.2f} m/paso). "
            "El conteo no parece fiable; no se guardaron métricas. Sube un video donde se vean claramente "
            "ambos pies durante toda la salida y el recorrido."
        )
    return step_length


class ProcessVideoFrames:
    """Procesa el video, valida que haya detecciones utilizables y persiste
    métricas solo cuando la pose y los datos de carrera son suficientes."""

    def __init__(
        self,
        video_repository: VideoRepository,
        test_repository: TestRepository,
        analysis_repository: AnalysisRepository,
        metrics_repository: MetricsRepository,
        frame_metrics_repository: FrameMetricsRepository,
        video_storage: VideoStorage,
        frame_processor: FrameProcessor,
        pose_estimator: PoseEstimator,
        metrics_calculator: MetricsCalculator,
        calibrator_factory: CalibratorFactory,
    ) -> None:
        self._video_repository = video_repository
        self._test_repository = test_repository
        self._analysis_repository = analysis_repository
        self._metrics_repository = metrics_repository
        self._frame_metrics_repository = frame_metrics_repository
        self._video_storage = video_storage
        self._frame_processor = frame_processor
        self._pose_estimator = pose_estimator
        self._metrics_calculator = metrics_calculator
        self._calibrator_factory = calibrator_factory
        self.pose_results: list[PoseEstimationResult] = []
        self.metrics_result: MetricsResult | None = None

    async def execute(self, analysis_id: int, video_id: int) -> Analysis:
        video = await self._video_repository.get_by_id(video_id)
        if video is None:
            return await self._analysis_repository.update_progress(
                analysis_id, AnalysisStatus.FAILED, 0, error_message=f"No existe un video con id={video_id}"
            )

        await self._analysis_repository.update_progress(analysis_id, AnalysisStatus.PROCESSING, processed_frames=0)
        absolute_path = self._video_storage.get_absolute_path(video.storage_path)
        processed_frames = 0
        last_timestamp_ms = -1
        self.pose_results = []
        self.metrics_result = None
        frame_iterator = self._frame_processor.iterate_frames(absolute_path)
        frame_step = _analysis_frame_step(video.fps)

        try:
            try:
                while True:
                    item = await asyncio.to_thread(_advance_iterator, frame_iterator)
                    if item is _ITERATOR_EXHAUSTED:
                        break
                    frame_number, frame, timestamp = item
                    if frame is None:
                        raise VideoProcessingError(f"Cuadro {frame_number} ilegible durante el procesamiento")
                    processed_frames = frame_number + 1
                    if frame_number % frame_step == 0:
                        timestamp_ms = max(round(timestamp * 1000), last_timestamp_ms + 1)
                        last_timestamp_ms = timestamp_ms
                        pose_result = await asyncio.to_thread(
                            self._pose_estimator.estimate, frame, frame_number, timestamp_ms
                        )
                        self.pose_results.append(dataclasses.replace(pose_result, timestamp=timestamp))
                    if processed_frames % _PROGRESS_UPDATE_EVERY == 0:
                        await self._analysis_repository.update_progress(
                            analysis_id, AnalysisStatus.PROCESSING, processed_frames
                        )
            finally:
                self._pose_estimator.close()
        except Exception as exc:
            logger.exception("Falló el procesamiento del análisis id=%s", analysis_id)
            return await self._analysis_repository.update_progress(
                analysis_id, AnalysisStatus.FAILED, processed_frames, error_message=str(exc)
            )

        if not any(result.keypoints for result in self.pose_results):
            return await self._analysis_repository.update_progress(
                analysis_id,
                AnalysisStatus.FAILED,
                processed_frames,
                error_message=(
                    "No se detectó ninguna persona. Cambia el video y comprueba que el atleta "
                    "se vea completo, enfocado y con buena iluminación."
                ),
            )

        try:
            await self._calculate_and_persist_metrics(video, analysis_id)
        except Exception as exc:
            logger.exception("Falló el cálculo de métricas del análisis id=%s", analysis_id)
            return await self._analysis_repository.update_progress(
                analysis_id,
                AnalysisStatus.FAILED,
                processed_frames,
                error_message=f"No se pudieron calcular métricas fiables: {exc}",
            )

        return await self._analysis_repository.update_progress(
            analysis_id, AnalysisStatus.COMPLETED, processed_frames
        )

    async def _calculate_and_persist_metrics(self, video: Video, analysis_id: int) -> None:
        test = await self._test_repository.get_by_id(video.test_id)
        reference_distance_m = float(test.distance) if test is not None else 10.0
        try:
            calibrator = self._calibrator_factory(video, reference_distance_m)
        except ValueError as exc:
            raise VideoProcessingError(f"No se pudo calibrar el video: {exc}") from exc

        run_window = None
        if video.run_start_s is not None and video.run_end_s is not None:
            run_window = (video.run_start_s, video.run_end_s)
            if video.duration and run_window[1] > video.duration + 0.05:
                raise VideoProcessingError(
                    "La llegada marcada está después del final del video. Marca salida y llegada "
                    "dentro de la duración real o sube el video completo."
                )

        if reference_distance_m >= TRACKING_CAMERA_MIN_DISTANCE_M:
            metric_poses = simulate_tracking_camera_progress(
                self.pose_results, calibrator, reference_distance_m, run_window
            )
        else:
            metric_poses = self.pose_results
            calibrator = calibrate_to_trajectory(self.pose_results, calibrator, reference_distance_m, run_window)

        summary_poses = (
            [pose for pose in metric_poses if run_window[0] <= pose.timestamp <= run_window[1]]
            if run_window is not None
            else metric_poses
        )
        usable_poses = [pose for pose in summary_poses if _has_valid_hips(pose)]
        required_poses = max(_MIN_VALID_HIP_FRAMES, math.ceil(len(summary_poses) * _MIN_POSE_COVERAGE))
        if len(usable_poses) < required_poses:
            raise VideoProcessingError(
                "No se detectó el cuerpo completo con suficiente claridad para medir la carrera. "
                "Cambia el video: muestra al atleta completo, de lado, enfocado y con buena iluminación."
            )

        self.metrics_result = self._metrics_calculator.calculate(summary_poses, calibrator)
        if (
            not math.isfinite(self.metrics_result.average_speed)
            or not math.isfinite(self.metrics_result.maximum_speed)
            or self.metrics_result.average_speed < 0
            or self.metrics_result.maximum_speed < 0
            or self.metrics_result.average_speed > _MAX_PLAUSIBLE_SPEED_MS
            or self.metrics_result.maximum_speed > _MAX_PLAUSIBLE_SPEED_MS
        ):
            raise VideoProcessingError(
                "La velocidad calculada es imposible (>15 m/s). No se guardaron resultados; "
                "revisa la distancia, las marcas de salida/llegada o cambia el video."
            )

        if (
            not math.isfinite(self.metrics_result.cadence)
            or self.metrics_result.cadence < _MIN_CADENCE_STEPS_PER_SECOND
            or not math.isfinite(self.metrics_result.stride_length)
            or self.metrics_result.stride_length <= 0
            or self.metrics_result.step_count is None
        ):
            raise VideoProcessingError(
                "No se detectaron suficientes pasos y apoyos para calcular la carrera. "
                "Cambia el video por uno donde se vean claramente las piernas y los pies."
            )

        duration_s = (
            run_duration_seconds(
                self.pose_results,
                run_window,
                use_trajectory_extremes=reference_distance_m < TRACKING_CAMERA_MIN_DISTANCE_M,
            )
            if run_window is not None
            else None
        )
        if duration_s is not None:
            average_speed = reference_distance_m / duration_s
            if not math.isfinite(average_speed) or average_speed > _MAX_PLAUSIBLE_SPEED_MS:
                raise VideoProcessingError(
                    "La velocidad calculada es imposible (>15 m/s). Revisa la distancia y las marcas "
                    "de salida/llegada, o cambia el video."
                )
            self.metrics_result = dataclasses.replace(
                self.metrics_result,
                average_speed=average_speed,
                maximum_speed=max(self.metrics_result.maximum_speed, average_speed),
                step_count=max(1, round(self.metrics_result.cadence * duration_s)),
            )

        # For short trials calculate mean step length from the known trial
        # distance and the detected step count, not the partial distance between
        # detected foot-strike peaks. This makes the displayed count and length
        # internally consistent (10 m / 7 steps = 1.43 m/step). If the inferred
        # count implies an implausible acceleration step length, fail instead of
        # silently showing a misleading value.
        self.metrics_result = dataclasses.replace(
            self.metrics_result,
            stride_length=_distance_per_detected_step(reference_distance_m, self.metrics_result.step_count),
        )

        await self._metrics_repository.create(
            Metrics(
                analysis_id=analysis_id,
                average_speed=self.metrics_result.average_speed,
                maximum_speed=self.metrics_result.maximum_speed,
                stride_length=self.metrics_result.stride_length,
                cadence=self.metrics_result.cadence,
                posture_score=self.metrics_result.posture_score,
                step_count=self.metrics_result.step_count,
            )
        )

        pose_by_frame = {result.frame_number: result for result in self.pose_results}
        frame_values = self._metrics_calculator.calculate_frame_metrics(metric_poses, calibrator)
        await self._frame_metrics_repository.bulk_create(
            [
                FrameMetrics(
                    analysis_id=analysis_id,
                    frame_number=fv.frame_number,
                    timestamp=fv.timestamp,
                    x_position=fv.x_position,
                    y_position=fv.y_position,
                    speed=fv.speed,
                    stride_phase=fv.stride_phase,
                    posture_score=fv.posture_score,
                    keypoints=[
                        {
                            "name": keypoint.name,
                            "x": keypoint.x,
                            "y": keypoint.y,
                            "confidence": keypoint.confidence,
                        }
                        for keypoint in pose_by_frame[fv.frame_number].keypoints
                    ],
                )
                for fv in frame_values
            ]
        )
