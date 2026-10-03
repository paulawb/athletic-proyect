import asyncio
import dataclasses
import logging
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
from app.domain.services.pose_estimator import PoseEstimationResult, PoseEstimator
from app.domain.services.video_storage import VideoStorage

logger = logging.getLogger(__name__)

# Cada cuantos cuadros se reporta el avance (seccion 22). Reportar cuadro a
# cuadro golpearia la base de datos innecesariamente en un video de miles
# de frames; cada 10 es un punto medio razonable para esta fase.
_PROGRESS_UPDATE_EVERY = 10

_ITERATOR_EXHAUSTED = object()

# El calibrador depende de datos propios de cada video (ancho/alto) y de la
# prueba (distancia de referencia), asi que no se puede construir una sola
# vez como pose_estimator o metrics_calculator -por eso se inyecta una
# FABRICA, no una instancia. Quien arma esta fabrica (el router) sí puede
# conocer las implementaciones concretas de infraestructura
# (LinearCoordinateCalibrator, HomographyCoordinateCalibrator); este caso
# de uso solo conoce la interfaz CoordinateCalibrator (seccion 11).
CalibratorFactory = Callable[[Video, float], CoordinateCalibrator]


def _advance_iterator(iterator):
    """Ejecuta next(iterator) de forma segura para cruzar un hilo (seccion 8:
    FrameProcessor.iterate_frames() usa cv2, que es sincrono y bloqueante).
    Atrapa StopIteration ACA, antes de cruzar el hilo: dejarla propagar tal
    cual hacia la coroutine que hace el await viola PEP 479 (una
    StopIteration que llega a una coroutine se convierte en RuntimeError)."""
    try:
        return next(iterator)
    except StopIteration:
        return _ITERATOR_EXHAUSTED


class ProcessVideoFrames:
    """Caso de uso de las Fases 4 a 10: recorre un Analysis ya creado
    (CreateAnalysis, Fase 8) cuadro por cuadro con FrameProcessor (seccion 8),
    estima la pose de cada cuadro con PoseEstimator (seccion 9,
    MockPoseEstimator o MediaPipePoseEstimator segun POSE_ESTIMATOR_BACKEND),
    calibra y calcula metricas con CoordinateCalibrator + MetricsCalculator
    (secciones 10-11, backends elegibles por configuracion desde la Fase 10),
    las persiste en Metrics y FrameMetrics (Fase 7), y deja registrado el
    avance en Analysis. self.pose_results y self.metrics_result quedan
    disponibles despues de execute() por si el llamador los necesita sin
    volver a consultar la base de datos.

    Se piensa para correr encolado con TaskRunner (Fase 8), no dentro del
    request HTTP: por eso ya no crea el Analysis (eso es CreateAnalysis,
    que sí corre sincronicamente porque es instantaneo) ni recibe la sesion
    HTTP en su ciclo de vida. Tanto el avance del iterador de cuadros como
    la estimacion de pose por cuadro se delegan a un hilo (asyncio.to_thread)
    para no bloquear el event loop mientras procesa -relevante sobre todo
    desde que PoseEstimator puede ser un modelo real (Fase 9), no el Mock
    trivial de la Fase 5. Sigue siendo el mismo proceso que la API
    (limitacion documentada en BackgroundTasksRunner), pero al menos no
    monopoliza el unico hilo del event loop durante todo el video.
    """

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
            # CreateAnalysis ya valido que el video existiera al crear este
            # Analysis; si de todos modos desaparecio (ej. lo borraron entre
            # medio), no se pierde el error: el analisis queda FAILED.
            return await self._analysis_repository.update_progress(
                analysis_id, AnalysisStatus.FAILED, 0, error_message=f"No existe un video con id={video_id}"
            )

        await self._analysis_repository.update_progress(analysis_id, AnalysisStatus.PROCESSING, processed_frames=0)

        absolute_path = self._video_storage.get_absolute_path(video.storage_path)
        processed_frames = 0
        self.pose_results = []
        self.metrics_result = None
        frame_iterator = self._frame_processor.iterate_frames(absolute_path)

        try:
            try:
                while True:
                    item = await asyncio.to_thread(_advance_iterator, frame_iterator)
                    if item is _ITERATOR_EXHAUSTED:
                        break
                    frame_number, frame, timestamp = item

                    if frame is None:
                        raise VideoProcessingError(
                            f"Cuadro {frame_number} ilegible durante el procesamiento"
                        )

                    # Los resultados de pose son livianos (unos pocos puntos
                    # por cuadro) a diferencia del cuadro de video en si;
                    # acumularlos aqui no repite el problema que
                    # iterate_frames() evita (nunca cargar el video completo
                    # en memoria). La estimacion en si se delega a un hilo
                    # igual que la lectura del cuadro: con MockPoseEstimator
                    # (Fase 5) era trivial, pero un modelo real (Fase 9,
                    # MediaPipePoseEstimator) sí puede tardar lo suficiente
                    # por cuadro como para bloquear el event loop si se
                    # llamara directamente.
                    pose_result = await asyncio.to_thread(
                        self._pose_estimator.estimate, frame, frame_number, round(timestamp * 1000)
                    )
                    self.pose_results.append(dataclasses.replace(pose_result, timestamp=timestamp))

                    processed_frames = frame_number + 1
                    if processed_frames % _PROGRESS_UPDATE_EVERY == 0:
                        await self._analysis_repository.update_progress(
                            analysis_id, AnalysisStatus.PROCESSING, processed_frames
                        )
            finally:
                # Libera el modelo subyacente (ej. el grafo de MediaPipe) en
                # cuanto se deja de necesitar, haya terminado bien o mal el
                # recorrido. MockPoseEstimator no tiene nada que liberar
                # (close() por defecto es un no-op en la interfaz).
                self._pose_estimator.close()
        except Exception as exc:
            logger.exception("Fallo el procesamiento del analisis id=%s", analysis_id)
            return await self._analysis_repository.update_progress(
                analysis_id, AnalysisStatus.FAILED, processed_frames, error_message=str(exc)
            )

        detected_frames = sum(bool(result.keypoints) for result in self.pose_results)
        if detected_frames == 0:
            return await self._analysis_repository.update_progress(
                analysis_id,
                AnalysisStatus.FAILED,
                processed_frames,
                error_message=(
                    "No se detectó ninguna persona en el video. Comprueba que el atleta "
                    "sea visible y tenga iluminación suficiente."
                ),
            )

        await self._calculate_and_persist_metrics(video, analysis_id)

        return await self._analysis_repository.update_progress(
            analysis_id, AnalysisStatus.COMPLETED, processed_frames
        )

    async def _calculate_and_persist_metrics(self, video: Video, analysis_id: int) -> None:
        if not self.pose_results:
            return

        test = await self._test_repository.get_by_id(video.test_id)
        reference_distance_m = float(test.distance) if test is not None else 10.0

        try:
            calibrator = self._calibrator_factory(video, reference_distance_m)
        except ValueError as exc:
            logger.warning("No se pudo calibrar (%s); se omite el calculo de metricas", exc)
            return

        self.metrics_result = self._metrics_calculator.calculate(self.pose_results, calibrator)
        await self._metrics_repository.create(
            Metrics(
                analysis_id=analysis_id,
                average_speed=self.metrics_result.average_speed,
                maximum_speed=self.metrics_result.maximum_speed,
                stride_length=self.metrics_result.stride_length,
                cadence=self.metrics_result.cadence,
                posture_score=self.metrics_result.posture_score,
            )
        )

        pose_by_frame = {result.frame_number: result for result in self.pose_results}
        frame_values = self._metrics_calculator.calculate_frame_metrics(self.pose_results, calibrator)
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
