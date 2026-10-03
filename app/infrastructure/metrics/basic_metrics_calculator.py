import math

from app.domain.services.metrics_calculator import (
    CoordinateCalibrator,
    FrameMetricValue,
    MetricsCalculator,
    MetricsResult,
)
from app.domain.services.pose_estimator import Keypoint, KeypointName, PoseEstimationResult

# Fase 9: estos ya no son strings locales, sino el mismo KeypointName que
# usan MockPoseEstimator y MediaPipePoseEstimator (dominio, pose_estimator.py).
# Si una implementacion nueva de PoseEstimator usara un nombre distinto para
# "cadera izquierda", esta busqueda simplemente no encontraria el punto -de
# ahi el valor de tener un unico vocabulario compartido en vez de que cada
# archivo repita el string por su cuenta.
_HIP_LEFT = KeypointName.LEFT_HIP
_HIP_RIGHT = KeypointName.RIGHT_HIP
_ANKLE_LEFT = KeypointName.LEFT_ANKLE
_NOSE = KeypointName.NOSE
_SHOULDER_LEFT = KeypointName.LEFT_SHOULDER
_SHOULDER_RIGHT = KeypointName.RIGHT_SHOULDER

_STANCE_PHASE = "apoyo"
_FLIGHT_PHASE = "vuelo"


class BasicMetricsCalculator(MetricsCalculator):
    """Primera implementacion de MetricsCalculator (seccion 10, Fase 6).

    Calcula velocidad y cadencia con formulas reales de cinematica
    (desplazamiento / tiempo) sobre los datos de pose que produce
    MockPoseEstimator (Fase 5): sigue el punto medio de las caderas cuadro
    a cuadro, lo convierte de pixeles a metros con el CoordinateCalibrator
    que reciba (seccion 11 -desde la Fase 10 puede ser una escala lineal o
    una homografia real; a esta clase no le importa cual), y divide por el
    tiempo entre cuadros. La postura usa una heuristica geometrica
    (alineacion nariz-hombros-cadera), no un modelo biomecanico real -para
    eso esta BiomechanicalMetricsCalculator (Fase 10).

    calculate() agrega todo el video en un solo MetricsResult (para la
    tabla METRICS); calculate_frame_metrics() devuelve el mismo calculo
    desglosado cuadro por cuadro (para FRAME_METRICS, Fase 7). Ambos
    comparten los mismos helpers internos para no duplicar formulas.
    """

    def calculate(
        self, pose_results: list[PoseEstimationResult], calibrator: CoordinateCalibrator
    ) -> MetricsResult:
        ordered = sorted(pose_results, key=lambda r: r.frame_number)
        if len(ordered) < 2:
            return MetricsResult(
                average_speed=0.0, maximum_speed=0.0, stride_length=0.0, cadence=0.0, posture_score=0.0
            )

        hip_positions_m = [self._hip_midpoint_in_meters(r, calibrator) for r in ordered]
        timestamps = [r.timestamp for r in ordered]

        speeds = [s for s in self._instantaneous_speeds(hip_positions_m, timestamps) if s is not None]
        average_speed = sum(speeds) / len(speeds) if speeds else 0.0
        maximum_speed = max(speeds) if speeds else 0.0

        stride_events = self._detect_stride_events(ordered)
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

        hip_positions_m = [self._hip_midpoint_in_meters(r, calibrator) for r in ordered]
        timestamps = [r.timestamp for r in ordered]
        instantaneous_speeds = self._instantaneous_speeds(hip_positions_m, timestamps)
        stride_events = set(self._detect_stride_events(ordered))

        values: list[FrameMetricValue] = []
        for i, result in enumerate(ordered):
            position = hip_positions_m[i]
            # El primer cuadro no tiene un cuadro anterior con el cual medir
            # desplazamiento, asi que no tiene velocidad instantanea propia.
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
            # Calibracion invalida (ej. LinearCoordinateCalibrator con
            # pixels_per_meter <= 0): se degrada con gracia -este cuadro no
            # aporta posicion- en vez de tumbar todo el calculo.
            return None

    @staticmethod
    def _instantaneous_speeds(
        positions: list[tuple[float, float] | None], timestamps: list[float]
    ) -> list[float | None]:
        """Una entrada por cada PAR de cuadros consecutivos (len(positions) - 1
        en total): speeds[i] es la velocidad entre el cuadro i y el i+1."""
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

    def _detect_stride_events(self, ordered: list[PoseEstimationResult]) -> list[int]:
        """Aproxima los apoyos como el punto mas bajo del tobillo en cada
        ciclo. En coordenadas de imagen 'mas abajo' es un valor de y mas
        grande (el eje crece hacia abajo), asi que se buscan maximos locales
        de ankle_y, no minimos. Comparacion estricta para no disparar en
        tramos planos. Un detector mas robusto (por velocidad, no solo
        posicion) esta en BiomechanicalMetricsCalculator (Fase 10)."""
        ankle_y = [
            (self._keypoint(r, _ANKLE_LEFT).y if self._keypoint(r, _ANKLE_LEFT) else None) for r in ordered
        ]
        events: list[int] = []
        for i in range(1, len(ankle_y) - 1):
            previous, current, following = ankle_y[i - 1], ankle_y[i], ankle_y[i + 1]
            if previous is None or current is None or following is None:
                continue
            if current > previous and current > following:
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
        nose = self._keypoint(result, _NOSE)
        left_shoulder = self._keypoint(result, _SHOULDER_LEFT)
        right_shoulder = self._keypoint(result, _SHOULDER_RIGHT)
        left_hip = self._keypoint(result, _HIP_LEFT)
        right_hip = self._keypoint(result, _HIP_RIGHT)
        if not all([nose, left_shoulder, right_shoulder, left_hip, right_hip]):
            return None

        shoulder_mid_x = (left_shoulder.x + right_shoulder.x) / 2
        hip_mid_x = (left_hip.x + right_hip.x) / 2
        hip_width = abs(left_hip.x - right_hip.x) or 1.0

        # Heuristica simple: entre mas alineados esten nariz, hombros y
        # cadera en el eje horizontal, mejor la puntuacion. No es un
        # modelo biomecanico real -para eso esta BiomechanicalMetricsCalculator
        # (Fase 10), que usa el angulo real de inclinacion del tronco.
        misalignment = (abs(nose.x - shoulder_mid_x) + abs(shoulder_mid_x - hip_mid_x)) / hip_width
        return max(0.0, 100.0 - misalignment * 50)
