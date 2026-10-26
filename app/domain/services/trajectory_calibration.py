import statistics

from app.domain.services.metrics_calculator import CoordinateCalibrator
from app.domain.services.pose_estimator import KeypointName, PoseEstimationResult

# Si la escala corregida difiere más que esto de la original, la suposición
# "el atleta recorre toda la distancia de la prueba" no se cumple (por ejemplo
# solo se grabó un tramo) y se conserva la calibración original.
_MIN_SCALE_FACTOR = 0.4
_MAX_SCALE_FACTOR = 2.5
_SMOOTHING_WINDOW = 5


class RescaledCalibrator(CoordinateCalibrator):
    def __init__(self, base: CoordinateCalibrator, factor: float) -> None:
        self._base = base
        self._factor = factor

    def pixel_to_world(self, x_px: float, y_px: float) -> tuple[float, float]:
        x, y = self._base.pixel_to_world(x_px, y_px)
        return x * self._factor, y * self._factor


def _hip_x_pixels(pose_results: list[PoseEstimationResult]) -> list[float]:
    values: list[float] = []
    for result in sorted(pose_results, key=lambda r: r.frame_number):
        by_name = {kp.name: kp for kp in result.keypoints}
        left, right = by_name.get(KeypointName.LEFT_HIP.value), by_name.get(KeypointName.RIGHT_HIP.value)
        if left is not None and right is not None:
            values.append((left.x + right.x) / 2)
    return values


def calibrate_to_trajectory(
    pose_results: list[PoseEstimationResult],
    calibrator: CoordinateCalibrator,
    reference_distance_m: float,
) -> CoordinateCalibrator:
    """Ajusta la escala para que el recorrido horizontal de la cadera, de la
    salida al final, equivalga a la distancia de la prueba. Requiere cámara
    fija y que el atleta recorra toda la distancia dentro del encuadre."""
    xs = _hip_x_pixels(pose_results)
    if len(xs) < _SMOOTHING_WINDOW * 2 or reference_distance_m <= 0:
        return calibrator
    half = _SMOOTHING_WINDOW // 2
    smoothed = [statistics.median(xs[max(0, i - half) : i + half + 1]) for i in range(len(xs))]
    try:
        traveled_m = abs(calibrator.pixel_to_world(max(smoothed), 0.0)[0] - calibrator.pixel_to_world(min(smoothed), 0.0)[0])
    except ValueError:
        return calibrator
    if traveled_m <= 0:
        return calibrator
    factor = reference_distance_m / traveled_m
    if not _MIN_SCALE_FACTOR <= factor <= _MAX_SCALE_FACTOR:
        return calibrator
    return RescaledCalibrator(calibrator, factor)
