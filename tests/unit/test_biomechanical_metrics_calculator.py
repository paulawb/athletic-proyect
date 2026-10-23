import math

import pytest

from app.domain.services.metrics_calculator import CameraCalibration
from app.domain.services.pose_estimator import Keypoint, PoseEstimationResult
from app.infrastructure.calibration.linear_coordinate_calibrator import LinearCoordinateCalibrator
from app.infrastructure.metrics.biomechanical_metrics_calculator import BiomechanicalMetricsCalculator


def _linear_calibrator(pixels_per_meter: float) -> LinearCoordinateCalibrator:
    return LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=pixels_per_meter))


def _pose_result(frame_number: int, hip_x: float, hip_y: float, ankle_y: float, timestamp: float):
    return PoseEstimationResult(
        frame_number=frame_number,
        timestamp=timestamp,
        keypoints=[
            Keypoint(name="left_hip", x=hip_x, y=hip_y, confidence=0.9),
            Keypoint(name="right_hip", x=hip_x, y=hip_y, confidence=0.9),
            Keypoint(name="left_ankle", x=hip_x, y=ankle_y, confidence=0.9),
        ],
    )


def _trunk_keypoints(hip_mid: tuple[float, float], shoulder_mid: tuple[float, float]) -> list[Keypoint]:
    hip_x, hip_y = hip_mid
    shoulder_x, shoulder_y = shoulder_mid
    return [
        Keypoint(name="left_shoulder", x=shoulder_x - 20, y=shoulder_y, confidence=0.9),
        Keypoint(name="right_shoulder", x=shoulder_x + 20, y=shoulder_y, confidence=0.9),
        Keypoint(name="left_hip", x=hip_x - 20, y=hip_y, confidence=0.9),
        Keypoint(name="right_hip", x=hip_x + 20, y=hip_y, confidence=0.9),
    ]


def test_calculate_computes_constant_speed_same_as_basic() -> None:
    """Velocidad y zancada usan el mismo CoordinateCalibrator.pixel_to_world()
    que BasicMetricsCalculator: el resultado deberia coincidir para el mismo
    movimiento simulado, solo cambia como se detectan los apoyos y la postura."""
    calculator = BiomechanicalMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    pose_results = [
        _pose_result(frame_number=i, hip_x=1000 + 20 * i, hip_y=500, ankle_y=700, timestamp=i * 0.1)
        for i in range(5)
    ]

    result = calculator.calculate(pose_results, calibrator)

    assert result.average_speed == pytest.approx(2.0, abs=0.01)
    assert result.maximum_speed == pytest.approx(2.0, abs=0.01)


def _running_pose_results(speed_ms: float = 3.0, steps_per_second: float = 5.0, noise: float = 0.0):
    """Corredor sintetico a 30 fps durante 3 s: la cadera avanza a velocidad
    constante y cada tobillo sube y baja en oposicion de fase."""
    pixels_per_meter = 100.0
    frequency = steps_per_second / 2
    results = []
    for i in range(90):
        t = i / 30
        hip_x = 100 + speed_ms * pixels_per_meter * t
        jitter = noise * (-1) ** i
        left_ankle_y = 700 + 60 * math.sin(2 * math.pi * frequency * t)
        right_ankle_y = 700 + 60 * math.sin(2 * math.pi * frequency * t + math.pi)
        results.append(
            PoseEstimationResult(
                frame_number=i,
                timestamp=t,
                keypoints=[
                    Keypoint(name="left_hip", x=hip_x + jitter, y=500, confidence=0.9),
                    Keypoint(name="right_hip", x=hip_x + jitter, y=500, confidence=0.9),
                    Keypoint(name="left_ankle", x=hip_x, y=left_ankle_y, confidence=0.9),
                    Keypoint(name="right_ankle", x=hip_x, y=right_ankle_y, confidence=0.9),
                ],
            )
        )
    return results


def test_calculate_detects_steps_of_both_feet_and_stride_length() -> None:
    calculator = BiomechanicalMetricsCalculator()

    result = calculator.calculate(_running_pose_results(), _linear_calibrator(100.0))

    assert result.cadence == pytest.approx(5.0, abs=0.3)
    # longitud de paso = 3 m/s / 5 pasos/s
    assert result.stride_length == pytest.approx(0.6, abs=0.05)
    assert result.average_speed == pytest.approx(3.0, abs=0.05)


def test_speed_is_not_inflated_by_detector_jitter() -> None:
    calculator = BiomechanicalMetricsCalculator()

    result = calculator.calculate(_running_pose_results(noise=2.0), _linear_calibrator(100.0))

    # +-2 px de temblor entre cuadros equivalen a ~3.6 m/s de velocidad falsa
    # si se resta cuadro a cuadro; el ajuste por ventana debe mantenerse cerca
    # de la velocidad real.
    assert result.average_speed == pytest.approx(3.0, abs=0.4)
    assert result.maximum_speed < 4.0


def test_standing_frames_do_not_lower_average_speed() -> None:
    calculator = BiomechanicalMetricsCalculator()
    standing = [
        PoseEstimationResult(
            frame_number=i,
            timestamp=i / 30,
            keypoints=[
                Keypoint(name="left_hip", x=100, y=500, confidence=0.9),
                Keypoint(name="right_hip", x=100, y=500, confidence=0.9),
            ],
        )
        for i in range(30)
    ]
    running = [
        PoseEstimationResult(frame_number=r.frame_number + 30, timestamp=r.timestamp + 1.0, keypoints=r.keypoints)
        for r in _running_pose_results()
    ]

    result = calculator.calculate(standing + running, _linear_calibrator(100.0))

    assert result.average_speed == pytest.approx(3.0, abs=0.1)


def test_frames_without_detection_have_no_speed() -> None:
    calculator = BiomechanicalMetricsCalculator()
    pose_results = _running_pose_results()
    pose_results[10] = PoseEstimationResult(frame_number=10, timestamp=10 / 30, keypoints=[])

    values = calculator.calculate_frame_metrics(pose_results, _linear_calibrator(100.0))

    assert values[10].speed == 0.0
    assert values[10].posture_score == 0.0
    assert values[11].speed == pytest.approx(3.0, abs=0.05)


def test_posture_score_is_perfect_at_ideal_drive_phase_lean() -> None:
    calculator = BiomechanicalMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    # cadera en (500,400), hombro en (700,200): dx=200, dy=-200 =>
    # angulo = atan2(200, 200) = 45 grados = el "ideal" de fase de impulso.
    keypoints = _trunk_keypoints(hip_mid=(500, 400), shoulder_mid=(700, 200))
    pose_results = [
        PoseEstimationResult(frame_number=0, timestamp=0.0, keypoints=keypoints),
        PoseEstimationResult(frame_number=1, timestamp=0.1, keypoints=keypoints),
    ]

    result = calculator.calculate(pose_results, calibrator)

    assert result.posture_score == pytest.approx(100.0, abs=0.5)


def test_posture_score_is_low_when_trunk_is_perfectly_upright() -> None:
    calculator = BiomechanicalMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    # torso perfectamente vertical (0 grados): 45 grados lejos del ideal de
    # fase de impulso -no es lo mismo que "buena postura" en este contexto.
    keypoints = _trunk_keypoints(hip_mid=(500, 400), shoulder_mid=(500, 200))
    pose_results = [
        PoseEstimationResult(frame_number=0, timestamp=0.0, keypoints=keypoints),
        PoseEstimationResult(frame_number=1, timestamp=0.1, keypoints=keypoints),
    ]

    result = calculator.calculate(pose_results, calibrator)

    assert result.posture_score == 0.0


def test_calculate_returns_zero_metrics_when_not_enough_data() -> None:
    calculator = BiomechanicalMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    result = calculator.calculate([], calibrator)

    assert result.average_speed == 0.0
    assert result.cadence == 0.0
    assert result.posture_score == 0.0


def test_calculate_frame_metrics_returns_one_entry_per_frame() -> None:
    calculator = BiomechanicalMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    pose_results = [
        _pose_result(frame_number=i, hip_x=1000 + 20 * i, hip_y=500, ankle_y=700, timestamp=i * 0.1)
        for i in range(5)
    ]

    frame_values = calculator.calculate_frame_metrics(pose_results, calibrator)

    assert [fv.frame_number for fv in frame_values] == [0, 1, 2, 3, 4]
