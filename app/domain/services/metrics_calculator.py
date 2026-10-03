from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.services.pose_estimator import PoseEstimationResult


@dataclass(frozen=True)
class CameraCalibration:
    """Valor simple de calibracion (seccion 11): una escala lineal
    pixeles-por-metro. LinearCoordinateCalibrator lo usa directamente;
    HomographyCoordinateCalibrator (Fase 10) usa puntos de referencia en
    su lugar -por eso CoordinateCalibrator ya no recibe este valor en
    cada llamada, sino que cada implementacion encapsula la suya."""

    pixels_per_meter: float
    reference_distance_m: float = 10.0


@dataclass(frozen=True)
class MetricsResult:
    average_speed: float
    maximum_speed: float
    stride_length: float
    cadence: float
    posture_score: float


@dataclass(frozen=True)
class FrameMetricValue:
    """Desglose por cuadro de las mismas metricas que MetricsResult agrega
    (seccion 6, tabla FRAME_METRICS). stride_phase es una etiqueta
    ('apoyo'/'vuelo'); BasicMetricsCalculator (Fase 6) la deriva de un
    maximo local simple, BiomechanicalMetricsCalculator (Fase 10) de un
    cruce por cero de la velocidad vertical del tobillo."""

    frame_number: int
    timestamp: float
    x_position: float
    y_position: float
    speed: float
    stride_phase: str
    posture_score: float


class CoordinateCalibrator(ABC):
    """Puerto de inversion de dependencia (seccion 11): convierte
    coordenadas de pixeles a coordenadas del mundo real (metros), sin que
    quien lo use sepa si por dentro hay una escala lineal simple
    (LinearCoordinateCalibrator) o una homografia con correccion de
    perspectiva (HomographyCoordinateCalibrator, Fase 10). Es stateful a
    proposito: la transformacion (ej. una matriz de homografia) se calcula
    una sola vez en el constructor de la implementacion concreta, no en
    cada cuadro."""

    @abstractmethod
    def pixel_to_world(self, x_px: float, y_px: float) -> tuple[float, float]:
        """Transforma un punto de pixeles a metros en el plano del suelo."""
        ...


class MetricsCalculator(ABC):
    @abstractmethod
    def calculate(
        self,
        pose_results: list[PoseEstimationResult],
        calibrator: CoordinateCalibrator,
    ) -> MetricsResult:
        """Encapsula las formulas reales; el endpoint nunca calcula nada
        directamente (seccion 10)."""
        ...

    @abstractmethod
    def calculate_frame_metrics(
        self,
        pose_results: list[PoseEstimationResult],
        calibrator: CoordinateCalibrator,
    ) -> list[FrameMetricValue]:
        """Igual que calculate(), pero devuelve el detalle cuadro por cuadro
        en vez del agregado. Se persiste en FRAME_METRICS (seccion 23: sirve
        para graficar la evolucion de cada variable durante el analisis)."""
        ...
