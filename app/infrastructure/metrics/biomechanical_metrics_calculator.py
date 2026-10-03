import math

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
_SHOULDER_LEFT = KeypointName.LEFT_SHOULDER
_SHOULDER_RIGHT = KeypointName.RIGHT_SHOULDER

_STANCE_PHASE = "apoyo"
_FLIGHT_PHASE = "vuelo"

# Referencia general de literatura de entrenamiento de velocidad para la
# FASE DE IMPULSO (salida de tacos, seccion 1): una inclinacion de tronco
# de ~40-50 grados desde la vertical es la que se asocia con una salida
# potente. No es un valor clinico exacto ni reemplaza una evaluacion
# biomecanica profesional -es una referencia razonable para dar una
# puntuacion con sentido, en vez de un numero arbitrario.
_IDEAL_DRIVE_PHASE_LEAN_DEG = 45.0
_LEAN_TOLERANCE_DEG = 20.0


class BiomechanicalMetricsCalculator(MetricsCalculator):
    """Segunda implementacion de MetricsCalculator (seccion 10, Fase 10):
    mejora las dos formulas que en BasicMetricsCalculator (Fase 6) eran
    heuristicas simples, sin cambiar la interfaz ni el resto del pipeline.

    POSTURA: en vez de solo alineacion horizontal nariz-hombros-cadera,
    calcula el angulo real de inclinacion del tronco (vector cadera-hombro
    contra la vertical) y lo compara con un rango ideal de la fase de
    impulso. Este angulo se mide en PIXELES, no en el mundo real
    calibrado: es una medida de ANGULO (invariante a escala), no de
    distancia, y solo tiene sentido si la camara tiene un componente
    lateral (de perfil) sobre el atleta -distinto del supuesto de vista
    cenital que usa CoordinateCalibrator para la distancia a lo largo de
    la pista. Ambos supuestos conviven porque miden cosas distintas con
    puntos distintos; ninguno de los dos es una calibracion 3D real de
    camara (eso excede el alcance de esta fase).

    CADENCIA / ZANCADA: detecta apoyos mediante el cruce por cero de la
    VELOCIDAD vertical del tobillo (positiva a negativa: deja de bajar y
    empieza a subir), en vez de comparar 3 puntos de posicion consecutivos
    (Fase 6). Es una tecnica estandar de deteccion de eventos de marcha a
    partir de pose 2D, mas robusta a ruido puntual porque mira la
    tendencia, no un pico aislado. Sigue sin ser deteccion real de
    contacto con el suelo (eso requeriria sensores de fuerza o un modelo
    entrenado especificamente para eso).

    Igual que BasicMetricsCalculator, VELOCIDAD y ZANCADA usan
    CoordinateCalibrator.pixel_to_world() para la posicion de la cadera,
    asi que se benefician automaticamente de una calibracion mejor
    (ej. HomographyCoordinateCalibrator) sin que esta clase cambie.
    """

    def calculate(
        self, pose_results: list[PoseEstimationResult], calibrator: CoordinateCalibrator
    ) -> MetricsResult:
        ordered = sorted(pose_results, key=lambda r: r.frame_number)
        if len(ordered) < 2:
            return MetricsResult(
                average_speed=0.0, maximum_speed=0.0, stride_length=0.0, cadence=0.0, posture_score=0.0
            )

        timestamps = [r.timestamp for r in ordered]
        hip_positions_m = [self._hip_midpoint_in_meters(r, calibrator) for r in ordered]

        speeds = [s for s in self._instantaneous_speeds(hip_positions_m, timestamps) if s is not None]
        average_speed = sum(speeds) / len(speeds) if speeds else 0.0
        maximum_speed = max(speeds) if speeds else 0.0

        stride_events = self._detect_stride_events(ordered, timestamps)
        stride_length = self._average_stride_length(hip_positions_m, stride_events)

        duration = timestamps[-1] - timestamps[0]
        cadence = (len(stride_events) / duration) if duration > 0 else 0.0

        posture_scores = [s for s in (self._posture_score_for_frame(r) for r in ordered) if s is not None]
        posture_score = sum(posture_scores) / len(posture_scores) if posture_scores else 0.0

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

        timestamps = [r.timestamp for r in ordered]
        hip_positions_m = [self._hip_midpoint_in_meters(r, calibrator) for r in ordered]
        instantaneous_speeds = self._instantaneous_speeds(hip_positions_m, timestamps)
        stride_events = set(self._detect_stride_events(ordered, timestamps))

        values: list[FrameMetricValue] = []
        for i, result in enumerate(ordered):
            position = hip_positions_m[i]
            speed = instantaneous_speeds[i - 1] if i > 0 and instantaneous_speeds[i - 1] is not None else 0.0
            posture_score = self._posture_score_for_frame(result) or 0.0

            values.append(
                FrameMetricValue(
                    frame_number=result.frame_number,
                    timestamp=result.timestamp,
                    x_position=round(position[0], 3) if position else 0.0,
                    y_position=round(position[1], 3) if position else 0.0,
                    speed=round(speed, 3),
                    stride_phase=_STANCE_PHASE if i in stride_events else _FLIGHT_PHASE,
                    posture_score=round(posture_score, 2),
                )
            )
        return values

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
        x_px = (left.x + right.x) / 2
        y_px = (left.y + right.y) / 2
        try:
            return calibrator.pixel_to_world(x_px, y_px)
        except ValueError:
            return None

    @staticmethod
    def _instantaneous_speeds(
        positions: list[tuple[float, float] | None], timestamps: list[float]
    ) -> list[float | None]:
        speeds: list[float | None] = []
        for i in range(1, len(positions)):
            previous, current = positions[i - 1], positions[i]
            delta_time = timestamps[i] - timestamps[i - 1]
            if previous is None or current is None or delta_time <= 0:
                speeds.append(None)
                continue
            distance = math.hypot(current[0] - previous[0], current[1] - previous[1])
            speeds.append(distance / delta_time)
        return speeds

    def _detect_stride_events(
        self, ordered: list[PoseEstimationResult], timestamps: list[float]
    ) -> list[int]:
        """Cruce por cero de la velocidad vertical del tobillo: positiva
        (bajando, y de imagen creciendo) a negativa o cero (subiendo) marca
        el punto mas bajo del ciclo -el apoyo simulado."""
        ankle_y = [
            (self._keypoint(r, _ANKLE_LEFT).y if self._keypoint(r, _ANKLE_LEFT) else None) for r in ordered
        ]

        velocities: list[float | None] = [None]
        for i in range(1, len(ankle_y)):
            delta_time = timestamps[i] - timestamps[i - 1]
            if ankle_y[i] is None or ankle_y[i - 1] is None or delta_time <= 0:
                velocities.append(None)
                continue
            velocities.append((ankle_y[i] - ankle_y[i - 1]) / delta_time)

        events: list[int] = []
        for i in range(1, len(velocities) - 1):
            entering, leaving = velocities[i], velocities[i + 1]
            if entering is None or leaving is None:
                continue
            if entering > 0 and leaving <= 0:
                events.append(i)
        return events

    @staticmethod
    def _average_stride_length(
        hip_positions_m: list[tuple[float, float] | None], stride_events: list[int]
    ) -> float:
        if len(stride_events) < 2:
            return 0.0
        distances = []
        for start, end in zip(stride_events, stride_events[1:]):
            position_start, position_end = hip_positions_m[start], hip_positions_m[end]
            if position_start is None or position_end is None:
                continue
            distances.append(math.hypot(position_end[0] - position_start[0], position_end[1] - position_start[1]))
        return sum(distances) / len(distances) if distances else 0.0

    def _posture_score_for_frame(self, result: PoseEstimationResult) -> float | None:
        angle = self._trunk_lean_angle_degrees(result)
        if angle is None:
            return None
        deviation = abs(angle - _IDEAL_DRIVE_PHASE_LEAN_DEG)
        return max(0.0, 100.0 - (deviation / _LEAN_TOLERANCE_DEG) * 100.0)

    def _trunk_lean_angle_degrees(self, result: PoseEstimationResult) -> float | None:
        """Angulo entre el vector cadera->hombro y la vertical, en grados.
        0 grados = torso perfectamente erguido; mayor angulo = mas
        inclinado hacia adelante. Medido en pixeles a proposito (ver
        docstring de la clase)."""
        left_shoulder = self._keypoint(result, _SHOULDER_LEFT)
        right_shoulder = self._keypoint(result, _SHOULDER_RIGHT)
        left_hip = self._keypoint(result, _HIP_LEFT)
        right_hip = self._keypoint(result, _HIP_RIGHT)
        if not all([left_shoulder, right_shoulder, left_hip, right_hip]):
            return None

        shoulder_mid_x = (left_shoulder.x + right_shoulder.x) / 2
        shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2
        hip_mid_x = (left_hip.x + right_hip.x) / 2
        hip_mid_y = (left_hip.y + right_hip.y) / 2

        dx = shoulder_mid_x - hip_mid_x
        dy = shoulder_mid_y - hip_mid_y  # negativo si el hombro esta mas arriba (imagen: y crece hacia abajo)
        if dx == 0 and dy == 0:
            return None

        return math.degrees(math.atan2(abs(dx), -dy))
