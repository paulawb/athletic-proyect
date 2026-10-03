from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import numpy as np


class KeypointName(str, Enum):
    """Vocabulario de nombres de puntos corporales que el resto del sistema
    (BasicMetricsCalculator, Fase 6) espera encontrar en Keypoint.name.
    Cualquier PoseEstimator -MockPoseEstimator, MediaPipePoseEstimator
    (Fase 9), YOLOPoseEstimator despues- debe usar estos mismos valores
    para que MetricsCalculator no tenga que saber nada de la
    implementacion concreta. Antes de la Fase 9 estos nombres vivian como
    strings sueltos duplicados en cada implementacion; centralizarlos aqui
    evita que un typo en una implementacion nueva rompa el calculo de
    metricas en silencio (una busqueda por nombre que nunca encuentra el
    punto, en vez de un error claro)."""

    NOSE = "nose"
    LEFT_SHOULDER = "left_shoulder"
    RIGHT_SHOULDER = "right_shoulder"
    LEFT_ELBOW = "left_elbow"
    RIGHT_ELBOW = "right_elbow"
    LEFT_WRIST = "left_wrist"
    RIGHT_WRIST = "right_wrist"
    LEFT_HIP = "left_hip"
    RIGHT_HIP = "right_hip"
    LEFT_KNEE = "left_knee"
    RIGHT_KNEE = "right_knee"
    LEFT_ANKLE = "left_ankle"
    RIGHT_ANKLE = "right_ankle"


@dataclass(frozen=True)
class Keypoint:
    name: str
    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class PoseEstimationResult:
    frame_number: int
    keypoints: list[Keypoint]
    # Segundos desde el inicio del video. FrameProcessor.iterate_frames() ya
    # lo produce por cuadro (seccion 8); ProcessVideoFrames lo adjunta aqui
    # porque MetricsCalculator (Fase 6) necesita el tiempo entre cuadros para
    # calcular velocidad real a partir de desplazamiento/tiempo (seccion 10).
    # El estimador de pose en si no lo necesita para detectar una pose en una
    # sola imagen, por eso no es parametro de estimate().
    timestamp: float = 0.0


class PoseEstimator(ABC):
    """Puerto de inversion de dependencia (seccion 9). MockPoseEstimator es la
    primera implementacion; MediaPipePoseEstimator (Fase 9) o
    YOLOPoseEstimator llegan despues sin tocar ningun caso de uso."""

    @abstractmethod
    def estimate(
        self, frame: np.ndarray, frame_number: int, timestamp_ms: int | None = None
    ) -> PoseEstimationResult: ...

    def close(self) -> None:
        """Libera recursos del modelo subyacente, si los hay. Implementacion
        por defecto: no-op (MockPoseEstimator no tiene nada que liberar).
        MediaPipePoseEstimator la sobreescribe para cerrar el grafo de
        MediaPipe correctamente; ProcessVideoFrames la llama siempre en un
        finally, sin necesidad de saber cual implementacion concreta recibe."""
        return None
