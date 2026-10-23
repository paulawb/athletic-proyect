import math
import statistics
from dataclasses import dataclass

from app.domain.services.metrics_calculator import (
    CoordinateCalibrator,
    FrameMetricValue,
    MetricsCalculator,
    MetricsResult,
)
from app.domain.services.pose_estimator import Keypoint, KeypointName, PoseEstimationResult

_HIP_LEFT = KeypointName.LEFT_HIP
_HIP_RIGHT = KeypointName.RIGHT_HIP
_ANKLE_LEFT = KeypointName.LEFT_ANKLE
_ANKLE_RIGHT = KeypointName.RIGHT_ANKLE
_SHOULDER_LEFT = KeypointName.LEFT_SHOULDER
_SHOULDER_RIGHT = KeypointName.RIGHT_SHOULDER

_STANCE_PHASE = "apoyo"
_FLIGHT_PHASE = "vuelo"

_EPSILON = 1e-9

# Ventana de suavizado: cada valor se calcula con un ajuste lineal por minimos
# cuadrados de los cuadros detectados en +-0.1 s. Elimina el temblor del
# detector sin sesgar movimientos de velocidad constante, y la pendiente del
# ajuste es la velocidad (no una resta de dos cuadros vecinos, que amplifica
# el ruido).
_SMOOTHING_HALF_WINDOW_S = 0.1

# Por debajo de esta velocidad el atleta se considera detenido (esperando la
# salida o ya frenado) y esos cuadros no entran en los promedios.
_MIN_MOVING_SPEED_MS = 0.5

# Deteccion de apoyos: maximo local de la altura del tobillo en la imagen.
_PEAK_HALF_WINDOW_S = 0.12
_PROMINENCE_WINDOW_S = 0.3
_MIN_PROMINENCE_LEG_FRACTION = 0.08
_MIN_SAME_FOOT_SEPARATION_S = 0.3

# Un pie se considera bien detectado si tiene al menos esta fraccion de los
# apoyos del otro.
_MIN_BALANCED_FOOT_RATIO = 0.6

# Postura: inclinacion del tronco respecto a la vertical. En la salida se
# espera ~45 grados y a medida que el atleta alcanza su velocidad maxima el
# tronco se va erguiendo hasta ~10 grados (referencia general de la
# literatura de entrenamiento de velocidad; no es una evaluacion clinica).
_START_LEAN_DEG = 45.0
_TOP_SPEED_LEAN_DEG = 10.0
_FULL_SCORE_TOLERANCE_DEG = 5.0
_ZERO_SCORE_DEVIATION_DEG = 25.0


@dataclass
class _Analysis:
    timestamps: list[float]
    positions: list[tuple[float, float] | None]
    speeds: list[float | None]
    left_strikes: list[int]
    right_strikes: list[int]
    postures: list[float | None]


class BiomechanicalMetricsCalculator(MetricsCalculator):
    """Calcula las metricas a partir de los puntos corporales detectados.

    Todos los valores salen de las posiciones medidas en el video:

    - VELOCIDAD: el promedio es la distancia neta de la cadera dividida por
      el tiempo desde que el atleta empieza a correr hasta que se detiene; el
      maximo es la mayor pendiente (m/s) del ajuste lineal de la posicion en
      una ventana de 0.2 s.
    - APOYOS: maximos locales de la altura de cada tobillo (el punto mas bajo
      del ciclo), con una amplitud minima relativa al largo de la pierna del
      propio atleta y una separacion minima entre apoyos del mismo pie.
    - CADENCIA: pasos por segundo entre el primer y el ultimo apoyo de la
      carrera. Si solo un pie se detecta bien, se cuentan sus ciclos x 2.
    - ZANCADA: longitud promedio de un paso (distancia de la cadera entre dos
      apoyos consecutivos); cadencia x zancada = velocidad.
    - POSTURA (%): que tan cerca esta la inclinacion del tronco de la
      esperada para la velocidad del momento, promediada en los cuadros en
      movimiento. 100 % = dentro de 5 grados de lo esperado; 0 % = 25 grados
      o mas de diferencia.

    La conversion de pixeles a metros la hace el CoordinateCalibrator; el
    angulo del tronco no depende de la escala, pero requiere una camara
    lateral (de perfil) al atleta.
    """

    def calculate(
        self, pose_results: list[PoseEstimationResult], calibrator: CoordinateCalibrator
    ) -> MetricsResult:
        ordered = sorted(pose_results, key=lambda r: r.frame_number)
        if len(ordered) < 2:
            return MetricsResult(
                average_speed=0.0, maximum_speed=0.0, stride_length=0.0, cadence=0.0, posture_score=0.0
            )

        analysis = self._analyze(ordered, calibrator)

        valid_speeds = [s for s in analysis.speeds if s is not None]
        maximum_speed = max(valid_speeds) if valid_speeds else 0.0

        run = self._run_segment(analysis)
        average_speed = self._average_speed(analysis, run, valid_speeds)
        cadence, stride_length = self._cadence_and_step_length(analysis, run)

        moving_postures = [
            posture
            for posture, speed in zip(analysis.postures, analysis.speeds)
            if posture is not None and speed is not None and speed >= _MIN_MOVING_SPEED_MS
        ]
        all_postures = [posture for posture in analysis.postures if posture is not None]
        postures_for_average = moving_postures or all_postures
        posture_score = sum(postures_for_average) / len(postures_for_average) if postures_for_average else 0.0

        return MetricsResult(
            average_speed=round(average_speed, 2),
            maximum_speed=round(maximum_speed, 2),
            stride_length=round(stride_length, 2),
            cadence=round(cadence, 2),
            posture_score=round(posture_score, 2),
        )

    def calculate_frame_metrics(
        self, pose_results: list[PoseEstimationResult], calibrator: CoordinateCalibrator
    ) -> list[FrameMetricValue]:
        ordered = sorted(pose_results, key=lambda r: r.frame_number)
        if not ordered:
            return []

        analysis = self._analyze(ordered, calibrator)
        strikes = set(analysis.left_strikes) | set(analysis.right_strikes)

        values: list[FrameMetricValue] = []
        for i, result in enumerate(ordered):
            position = analysis.positions[i]
            speed = analysis.speeds[i]
            posture = analysis.postures[i]
            values.append(
                FrameMetricValue(
                    frame_number=result.frame_number,
                    timestamp=result.timestamp,
                    x_position=round(position[0], 3) if position else 0.0,
                    y_position=round(position[1], 3) if position else 0.0,
                    speed=round(speed, 3) if speed is not None else 0.0,
                    stride_phase=_STANCE_PHASE if i in strikes else _FLIGHT_PHASE,
                    posture_score=round(posture, 2) if posture is not None else 0.0,
                )
            )
        return values

    def _analyze(self, ordered: list[PoseEstimationResult], calibrator: CoordinateCalibrator) -> _Analysis:
        timestamps = [r.timestamp for r in ordered]
        raw_positions = [self._hip_midpoint_in_meters(r, calibrator) for r in ordered]
        raw_x = [p[0] if p else None for p in raw_positions]
        raw_y = [p[1] if p else None for p in raw_positions]

        positions: list[tuple[float, float] | None] = []
        speeds: list[float | None] = []
        for i in range(len(ordered)):
            fit_x = _local_fit(raw_x, timestamps, i, _SMOOTHING_HALF_WINDOW_S)
            fit_y = _local_fit(raw_y, timestamps, i, _SMOOTHING_HALF_WINDOW_S)
            if fit_x is None or fit_y is None:
                positions.append(None)
                speeds.append(None)
                continue
            positions.append((fit_x[0], fit_y[0]))
            speeds.append(math.hypot(fit_x[1], fit_y[1]))

        valid_speeds = [s for s in speeds if s is not None]
        top_speed = max(valid_speeds) if valid_speeds else 0.0

        raw_angles = [self._trunk_lean_angle_degrees(r) for r in ordered]
        postures: list[float | None] = []
        for i in range(len(ordered)):
            fit = _local_fit(raw_angles, timestamps, i, _SMOOTHING_HALF_WINDOW_S)
            if fit is None:
                postures.append(None)
                continue
            speed = speeds[i] or 0.0
            speed_ratio = min(1.0, speed / top_speed) if top_speed > 0 else 0.0
            ideal = _START_LEAN_DEG - (_START_LEAN_DEG - _TOP_SPEED_LEAN_DEG) * speed_ratio
            postures.append(_posture_percentage(abs(fit[0] - ideal)))

        return _Analysis(
            timestamps=timestamps,
            positions=positions,
            speeds=speeds,
            left_strikes=self._foot_strikes(ordered, timestamps, _ANKLE_LEFT),
            right_strikes=self._foot_strikes(ordered, timestamps, _ANKLE_RIGHT),
            postures=postures,
        )

    @staticmethod
    def _keypoint(result: PoseEstimationResult, name: str) -> Keypoint | None:
        return next((kp for kp in result.keypoints if kp.name == name), None)

    def _hip_midpoint_in_meters(
        self, result: PoseEstimationResult, calibrator: CoordinateCalibrator
    ) -> tuple[float, float] | None:
        left = self._keypoint(result, _HIP_LEFT)
        right = self._keypoint(result, _HIP_RIGHT)
        if left is None or right is None:
            return None
        try:
            return calibrator.pixel_to_world((left.x + right.x) / 2, (left.y + right.y) / 2)
        except ValueError:
            return None

    def _foot_strikes(
        self, ordered: list[PoseEstimationResult], timestamps: list[float], ankle_name: str
    ) -> list[int]:
        """Indices de los cuadros donde el tobillo esta en su punto mas bajo."""
        ankle_y = [(kp.y if (kp := self._keypoint(r, ankle_name)) else None) for r in ordered]
        smoothed: list[float | None] = []
        for i in range(len(ankle_y)):
            fit = _local_fit(ankle_y, timestamps, i, _SMOOTHING_HALF_WINDOW_S)
            smoothed.append(fit[0] if fit else None)

        leg_lengths = []
        for result, y in zip(ordered, smoothed):
            left_hip = self._keypoint(result, _HIP_LEFT)
            right_hip = self._keypoint(result, _HIP_RIGHT)
            if y is not None and left_hip and right_hip:
                length = y - (left_hip.y + right_hip.y) / 2
                if length > 0:
                    leg_lengths.append(length)
        min_prominence = _MIN_PROMINENCE_LEG_FRACTION * statistics.median(leg_lengths) if leg_lengths else 0.0

        candidates: list[int] = []
        for i, y in enumerate(smoothed):
            if y is None:
                continue
            window = [
                (j, smoothed[j])
                for j in _indices_within(timestamps, i, _PEAK_HALF_WINDOW_S)
                if smoothed[j] is not None
            ]
            if not any(j < i for j, _ in window) or not any(j > i for j, _ in window):
                continue
            highest = max(value for _, value in window)
            if next(j for j, value in window if value == highest) != i:
                continue
            wide = [
                smoothed[j]
                for j in _indices_within(timestamps, i, _PROMINENCE_WINDOW_S)
                if smoothed[j] is not None
            ]
            if y - min(wide) < min_prominence:
                continue
            candidates.append(i)

        kept: list[int] = []
        for index in candidates:
            if kept and timestamps[index] - timestamps[kept[-1]] < _MIN_SAME_FOOT_SEPARATION_S:
                if smoothed[index] > smoothed[kept[-1]]:
                    kept[-1] = index
                continue
            kept.append(index)
        return kept

    @staticmethod
    def _run_segment(analysis: _Analysis) -> tuple[int, int] | None:
        """Cuadros (primero, ultimo) en que el atleta va corriendo: desde que
        arranca hasta que deja de moverse. Excluye la espera previa a la salida
        y el frenado final."""
        moving = [i for i, s in enumerate(analysis.speeds) if s is not None and s >= _MIN_MOVING_SPEED_MS]
        if len(moving) < 2:
            return None
        return moving[0], moving[-1]

    @staticmethod
    def _average_speed(
        analysis: _Analysis, run: tuple[int, int] | None, valid_speeds: list[float]
    ) -> float:
        """Distancia neta recorrida por la cadera / tiempo desde que empezo a
        correr. Promediar velocidades instantaneas infla el resultado con el
        temblor del detector."""
        if run is not None:
            start, end = run
            first, last = analysis.positions[start], analysis.positions[end]
            elapsed = analysis.timestamps[end] - analysis.timestamps[start]
            if first is not None and last is not None and elapsed > 0:
                return math.hypot(last[0] - first[0], last[1] - first[1]) / elapsed
        return sum(valid_speeds) / len(valid_speeds) if valid_speeds else 0.0

    @staticmethod
    def _cadence_and_step_length(analysis: _Analysis, run: tuple[int, int] | None) -> tuple[float, float]:
        """Cadencia (pasos/s) y longitud de paso (m) durante la carrera.

        Con camara de perfil la pierna lejana suele detectarse mal; si un pie
        tiene muchos menos apoyos que el otro, se usa solo el pie con mejor
        deteccion y se asume que los pasos alternan (un ciclo = 2 pasos)."""
        low, high = run if run is not None else (0, len(analysis.timestamps) - 1)

        def inside(strikes: list[int]) -> list[int]:
            return [i for i in strikes if low <= i <= high]

        left, right = inside(analysis.left_strikes), inside(analysis.right_strikes)
        fewer, more = sorted((left, right), key=len)
        balanced = len(more) > 0 and len(fewer) >= _MIN_BALANCED_FOOT_RATIO * len(more)

        if balanced:
            strikes = sorted(left + right)
            steps_per_cycle = 1
        else:
            strikes = more
            steps_per_cycle = 2
        if len(strikes) < 2:
            return 0.0, 0.0

        span = analysis.timestamps[strikes[-1]] - analysis.timestamps[strikes[0]]
        if span <= 0:
            return 0.0, 0.0
        intervals = len(strikes) - 1
        cadence = intervals * steps_per_cycle / span

        distance = 0.0
        for start, end in zip(strikes, strikes[1:]):
            position_start, position_end = analysis.positions[start], analysis.positions[end]
            if position_start is None or position_end is None:
                continue
            distance += math.hypot(position_end[0] - position_start[0], position_end[1] - position_start[1])
        step_length = distance / (intervals * steps_per_cycle)
        return cadence, step_length

    def _trunk_lean_angle_degrees(self, result: PoseEstimationResult) -> float | None:
        """Angulo entre el vector cadera->hombro y la vertical, en grados.
        0 = torso erguido; mayor angulo = mas inclinado. Se mide en pixeles
        porque un angulo no depende de la escala."""
        left_shoulder = self._keypoint(result, _SHOULDER_LEFT)
        right_shoulder = self._keypoint(result, _SHOULDER_RIGHT)
        left_hip = self._keypoint(result, _HIP_LEFT)
        right_hip = self._keypoint(result, _HIP_RIGHT)
        if not all([left_shoulder, right_shoulder, left_hip, right_hip]):
            return None

        dx = (left_shoulder.x + right_shoulder.x) / 2 - (left_hip.x + right_hip.x) / 2
        dy = (left_shoulder.y + right_shoulder.y) / 2 - (left_hip.y + right_hip.y) / 2
        if dx == 0 and dy == 0:
            return None
        return math.degrees(math.atan2(abs(dx), -dy))


def _posture_percentage(deviation_degrees: float) -> float:
    if deviation_degrees <= _FULL_SCORE_TOLERANCE_DEG:
        return 100.0
    span = _ZERO_SCORE_DEVIATION_DEG - _FULL_SCORE_TOLERANCE_DEG
    return max(0.0, 100.0 - (deviation_degrees - _FULL_SCORE_TOLERANCE_DEG) / span * 100.0)


def _indices_within(timestamps: list[float], center: int, half_window: float) -> list[int]:
    indices = [center]
    j = center - 1
    while j >= 0 and timestamps[center] - timestamps[j] <= half_window + _EPSILON:
        indices.append(j)
        j -= 1
    j = center + 1
    while j < len(timestamps) and timestamps[j] - timestamps[center] <= half_window + _EPSILON:
        indices.append(j)
        j += 1
    return sorted(indices)


def _local_fit(
    values: list[float | None], timestamps: list[float], center: int, half_window: float
) -> tuple[float, float] | None:
    """Recta de minimos cuadrados de los valores detectados alrededor de
    `center`. Devuelve (valor ajustado en el cuadro, pendiente por segundo)."""
    if values[center] is None:
        return None
    origin = timestamps[center]
    points = [
        (timestamps[j] - origin, values[j])
        for j in _indices_within(timestamps, center, half_window)
        if values[j] is not None
    ]
    if len(points) < 2:
        return None
    mean_t = sum(t for t, _ in points) / len(points)
    mean_v = sum(v for _, v in points) / len(points)
    variance = sum((t - mean_t) ** 2 for t, _ in points)
    if variance <= _EPSILON:
        return mean_v, 0.0
    slope = sum((t - mean_t) * (v - mean_v) for t, v in points) / variance
    return mean_v - slope * mean_t, slope
