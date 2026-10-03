from app.domain.services.metrics_calculator import CameraCalibration, CoordinateCalibrator


class LinearCoordinateCalibrator(CoordinateCalibrator):
    """Calibracion lineal simple (la que usabamos desde la Fase 6, ahora
    formalizada como una implementacion real de CoordinateCalibrator):
    asume que un metro representa siempre la misma cantidad de pixeles en
    toda la imagen, sin corregir perspectiva. Correcta solo si la camara
    mira perfectamente perpendicular al plano del suelo (nadir); con
    cualquier angulo real de dron, HomographyCoordinateCalibrator
    (Fase 10) es mas precisa."""

    def __init__(self, calibration: CameraCalibration) -> None:
        self._pixels_per_meter = calibration.pixels_per_meter

    def pixel_to_world(self, x_px: float, y_px: float) -> tuple[float, float]:
        if self._pixels_per_meter <= 0:
            raise ValueError("pixels_per_meter debe ser mayor que cero")
        return x_px / self._pixels_per_meter, y_px / self._pixels_per_meter
