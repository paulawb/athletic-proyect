import statistics
from dataclasses import replace

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
    run_window: tuple[float, float] | None = None,
) -> CoordinateCalibrator:
    """Ajusta la escala para que el recorrido horizontal de la cadera, de la
    salida al final, equivalga a la distancia de la prueba. Requiere cámara
    fija y que el atleta recorra toda la distancia dentro del encuadre.
    Con `run_window` (segundos de salida y llegada) solo se usa ese tramo."""
    if run_window is not None:
        pose_results = [r for r in pose_results if run_window[0] <= r.timestamp <= run_window[1]]
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


def run_duration_seconds(
    pose_results: list[PoseEstimationResult],
    run_window: tuple[float, float] | None,
    use_trajectory_extremes: bool,
) -> float | None:
    """Tiempo que tardó el atleta en cubrir la distancia de la prueba: la
    ventana marcada por el usuario o, si no hay, el intervalo entre el primer
    y el último punto del recorrido (cámara fija) o entre la primera y la
    última detección (cámara en seguimiento)."""
    if run_window is not None:
        duration = run_window[1] - run_window[0]
        return duration if duration > 0 else None
    detected = sorted(
        (r for r in pose_results if _hip_x_pixels([r])), key=lambda r: r.frame_number
    )
    if len(detected) < _SMOOTHING_WINDOW * 2:
        return None
    if use_trajectory_extremes:
        xs = _hip_x_pixels(detected)
        half = _SMOOTHING_WINDOW // 2
        smoothed = [statistics.median(xs[max(0, i - half) : i + half + 1]) for i in range(len(xs))]
        low, high = min(smoothed), max(smoothed)
        margin = 0.02 * (high - low)
        direction = 1 if smoothed[-1] >= smoothed[0] else -1
        if direction < 0:
            smoothed = [-v for v in smoothed]
            low, high = -high, -low
        try:
            start_idx = max(i for i, v in enumerate(smoothed) if v <= low + margin and i <= smoothed.index(max(smoothed)))
            end_idx = next(i for i, v in enumerate(smoothed) if v >= high - margin)
        except (ValueError, StopIteration):
            return None
        times = [detected[start_idx].timestamp, detected[end_idx].timestamp]
    else:
        times = [detected[0].timestamp, detected[-1].timestamp]
    duration = times[1] - times[0]
    return duration if duration > 0 else None


# Desde esta distancia la cámara acompaña al atleta, así que su posición en el
# cuadro casi no cambia y el desplazamiento no se puede medir en píxeles.
TRACKING_CAMERA_MIN_DISTANCE_M = 20.0


def simulate_tracking_camera_progress(
    pose_results: list[PoseEstimationResult],
    calibrator: CoordinateCalibrator,
    reference_distance_m: float,
    run_window: tuple[float, float] | None = None,
) -> list[PoseEstimationResult]:
    """Con cámara en seguimiento, suma a la x de cada cuadro el avance de una
    carrera que cubre la distancia de la prueba entre la salida y la llegada
    (velocidad media = distancia / tiempo). Sin `run_window` se usan la primera
    y la última detección; con ella, el atleta está quieto antes de la salida y
    parado tras la llegada. Solo para calcular métricas; los puntos originales
    no se modifican."""
    ordered = sorted(pose_results, key=lambda r: r.frame_number)
    timed = [r for r in ordered if _hip_x_pixels([r])]
    if len(timed) < _SMOOTHING_WINDOW * 2 or reference_distance_m <= 0:
        return pose_results
    t0, t1 = run_window if run_window is not None else (timed[0].timestamp, timed[-1].timestamp)
    if t1 - t0 <= 0:
        return pose_results
    anchor_x = _hip_x_pixels([timed[0]])[0]
    try:
        meters_per_px = calibrator.pixel_to_world(anchor_x + 1.0, 0.0)[0] - calibrator.pixel_to_world(anchor_x, 0.0)[0]
    except ValueError:
        return pose_results
    if meters_per_px <= 0:
        return pose_results
    px_total = reference_distance_m / meters_per_px

    shifted: list[PoseEstimationResult] = []
    for result in ordered:
        progress = min(max((result.timestamp - t0) / (t1 - t0), 0.0), 1.0)
        offset = px_total * progress
        shifted.append(
            replace(result, keypoints=[replace(kp, x=kp.x + offset) for kp in result.keypoints])
        )
    return shifted
