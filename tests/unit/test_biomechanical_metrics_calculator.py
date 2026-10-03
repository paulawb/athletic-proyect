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


def test_calculate_detects_stride_events_via_velocity_zero_crossing() -> None:
    calculator = BiomechanicalMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    # Mismo patron sintetico que en BasicMetricsCalculator: el metodo nuevo
    # (cruce por cero de la velocidad vertical) coincide en este caso limpio,
    # aunque es mas robusto a ruido puntual en casos menos ideales.
    ankle_y_values = [80, 100, 80, 100, 80]
    hip_x_values = [1000, 1010, 1020, 1030, 1040]
    pose_results = [
        _pose_result(
            frame_number=i, hip_x=hip_x_values[i], hip_y=500, ankle_y=ankle_y_values[i], timestamp=i * 0.1
        )
        for i in range(5)
    ]

    result = calculator.calculate(pose_results, calibrator)

    assert result.cadence == pytest.approx(5.0, abs=0.01)
    assert result.stride_length == pytest.approx(0.2, abs=0.01)


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
