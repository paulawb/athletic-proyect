import math

import numpy as np

from app.domain.services.pose_estimator import Keypoint, KeypointName, PoseEstimationResult, PoseEstimator

# Esqueleto reducido, suficiente para las 4 variables de desempeño (postura,
# velocidad, zancada, cadencia). Un modelo real (MediaPipe/YOLO, seccion 9)
# podria devolver mas puntos; los casos de uso no dependen de cuantos sean.
# Los nombres vienen de KeypointName (dominio), no de strings sueltos aqui:
# es el mismo vocabulario que usa MediaPipePoseEstimator (Fase 9).
_KEYPOINT_NAMES = tuple(KeypointName)

_MOCK_CONFIDENCE = 0.9


class MockPoseEstimator(PoseEstimator):
    """Primera implementacion de PoseEstimator (seccion 9).

    NO analiza el contenido real del cuadro: devuelve un esqueleto simulado
    que oscila segun el numero de cuadro, para que MetricsCalculator
    (Fase 6) tenga datos con forma de ciclo de carrera sobre los que probar
    sus calculos, en vez de puntos fijos sin sentido. MediaPipePoseEstimator
    o YOLOPoseEstimator la reemplazaran despues (Fase 9) sin que
    ProcessVideoFrames ni MetricsCalculator cambien: ambos dependen de la
    interfaz PoseEstimator, no de esta clase.
    """

    def estimate(
        self, frame: np.ndarray, frame_number: int, timestamp_ms: int | None = None
    ) -> PoseEstimationResult:
        height, width = self._frame_dimensions(frame)
        keypoints = [
            self._simulate_keypoint(index, frame_number, width, height)
            for index in range(len(_KEYPOINT_NAMES))
        ]
        return PoseEstimationResult(frame_number=frame_number, keypoints=keypoints)

    @staticmethod
    def _frame_dimensions(frame: np.ndarray) -> tuple[int, int]:
        if frame is not None and hasattr(frame, "shape") and len(frame.shape) >= 2:
            return int(frame.shape[0]), int(frame.shape[1])
        return 1080, 1920  # resolucion de respaldo si el frame no trae shape

    @staticmethod
    def _simulate_keypoint(index: int, frame_number: int, width: int, height: int) -> Keypoint:
        # Oscilacion simple para simular el ciclo de zancada: cada punto
        # tiene una fase distinta segun su posicion en el esqueleto, y todos
        # se mueven juntos a medida que avanza el video (frame_number).
        phase = index * 0.35
        stride_cycle = math.sin((frame_number * 0.3) + phase)

        x = (0.5 + 0.05 * stride_cycle) * width
        y = ((index + 1) / (len(_KEYPOINT_NAMES) + 1) + 0.02 * stride_cycle) * height

        return Keypoint(
            name=_KEYPOINT_NAMES[index].value, x=round(x, 2), y=round(y, 2), confidence=_MOCK_CONFIDENCE
        )
