import cv2
import numpy as np

from app.domain.services.metrics_calculator import CoordinateCalibrator

# Ancho estandar de un carril de pista de atletismo (reglamento World
# Athletics). Se usa solo como supuesto por defecto en from_frame_corners();
# una calibracion real con los 4 puntos correctos de la toma no lo necesita.
_STANDARD_LANE_WIDTH_M = 1.22


class HomographyCoordinateCalibrator(CoordinateCalibrator):
    """Implementacion real de CoordinateCalibrator (seccion 11): usa una
    homografia (transformacion de perspectiva, via OpenCV) en vez de
    asumir que los pixeles equivalen linealmente a metros en toda la
    imagen -relevante porque un dron rara vez queda perfectamente en
    nadir (perpendicular al suelo) sobre la pista.

    Necesita 4 puntos de referencia en pixeles (las esquinas de una zona
    plana conocida, ej. la pista vista desde el dron) y sus 4 equivalentes
    reales en metros. Esos puntos son especificos de cada toma -esta
    clase no los inventa, solo hace la transformacion una vez que los
    tiene.

    Mientras no exista una forma de marcarlos (a mano sobre el video, o
    con marcadores fisicos detectados automaticamente sobre la pista -
    ninguna de las dos esta en el alcance de esta fase), from_frame_corners()
    construye un calibrador con el mismo supuesto simplificado que ya
    usabamos desde la Fase 6 (el cuadro completo = la distancia de la
    prueba), pero corriendo sobre el mecanismo correcto: en cuanto haya
    puntos reales, mejora la precision sin tocar MetricsCalculator ni
    ProcessVideoFrames.
    """

    def __init__(
        self, pixel_points: list[tuple[float, float]], world_points: list[tuple[float, float]]
    ) -> None:
        if len(pixel_points) != 4 or len(world_points) != 4:
            raise ValueError("Se requieren exactamente 4 puntos de referencia (pixeles y metros)")

        source = np.array(pixel_points, dtype=np.float32)
        destination = np.array(world_points, dtype=np.float32)
        self._homography = cv2.getPerspectiveTransform(source, destination)

    @classmethod
    def from_frame_corners(
        cls,
        frame_width_px: int,
        frame_height_px: int,
        reference_distance_m: float,
        lane_width_m: float = _STANDARD_LANE_WIDTH_M,
    ) -> "HomographyCoordinateCalibrator":
        """Calibrador por defecto: asume que el cuadro completo es la vista
        de un rectangulo de reference_distance_m x lane_width_m. Es una
        simplificacion (no hay puntos de referencia reales de la toma
        todavia), documentada como tal -no una calibracion real de
        camara-, pero corre sobre la misma homografia que usaria una."""
        pixel_corners = [
            (0.0, 0.0),
            (float(frame_width_px), 0.0),
            (float(frame_width_px), float(frame_height_px)),
            (0.0, float(frame_height_px)),
        ]
        world_corners = [
            (0.0, 0.0),
            (reference_distance_m, 0.0),
            (reference_distance_m, lane_width_m),
            (0.0, lane_width_m),
        ]
        return cls(pixel_corners, world_corners)

    def pixel_to_world(self, x_px: float, y_px: float) -> tuple[float, float]:
        point = np.array([[[x_px, y_px]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self._homography)
        x_m, y_m = transformed[0][0]
        return float(x_m), float(y_m)
