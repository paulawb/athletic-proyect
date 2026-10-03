import pytest

from app.domain.services.metrics_calculator import CameraCalibration
from app.domain.services.pose_estimator import Keypoint, PoseEstimationResult
from app.infrastructure.calibration.linear_coordinate_calibrator import LinearCoordinateCalibrator
from app.infrastructure.metrics.basic_metrics_calculator import BasicMetricsCalculator


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


def test_calculate_returns_zero_metrics_when_not_enough_data() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    for pose_results in ([], [_pose_result(0, 1000, 500, 700, 0.0)]):
        result = calculator.calculate(pose_results, calibrator)

        assert result.average_speed == 0.0
        assert result.maximum_speed == 0.0
        assert result.stride_length == 0.0
        assert result.cadence == 0.0
        assert result.posture_score == 0.0


def test_calculate_computes_constant_speed_from_known_displacement() -> None:
    calculator = BasicMetricsCalculator()
    # 100 px = 1 m; la cadera avanza 20 px cada 0.1 s => 0.2 m / 0.1 s = 2.0 m/s
    calibrator = _linear_calibrator(100.0)

    pose_results = [
        _pose_result(frame_number=i, hip_x=1000 + 20 * i, hip_y=500, ankle_y=700, timestamp=i * 0.1)
        for i in range(5)
    ]

    result = calculator.calculate(pose_results, calibrator)

    assert result.average_speed == pytest.approx(2.0, abs=0.01)
    assert result.maximum_speed == pytest.approx(2.0, abs=0.01)


def test_calculate_detects_stride_events_and_computes_cadence_and_stride_length() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    # El tobillo sube-baja-sube-baja: un apoyo es un MAXIMO local de y en
    # pixeles (el eje de la imagen crece hacia abajo, asi que "mas cerca del
    # suelo" es un valor de y mas grande). Aqui hay apoyos en los indices 1
    # y 3. La cadera avanza 10 px por cuadro => entre esos dos apoyos
    # recorre 20 px = 0.2 m.
    ankle_y_values = [80, 100, 80, 100, 80]
    hip_x_values = [1000, 1010, 1020, 1030, 1040]

    pose_results = [
        _pose_result(
            frame_number=i, hip_x=hip_x_values[i], hip_y=500, ankle_y=ankle_y_values[i], timestamp=i * 0.1
        )
        for i in range(5)
    ]

    result = calculator.calculate(pose_results, calibrator)

    # 2 apoyos detectados en 0.4 s de duracion total = 5 pasos/s
    assert result.cadence == pytest.approx(5.0, abs=0.01)
    assert result.stride_length == pytest.approx(0.2, abs=0.01)


def test_calculate_gives_perfect_posture_score_when_points_are_vertically_aligned() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    aligned_keypoints = [
        Keypoint(name="nose", x=500.0, y=100.0, confidence=0.9),
        Keypoint(name="left_shoulder", x=480.0, y=200.0, confidence=0.9),
        Keypoint(name="right_shoulder", x=520.0, y=200.0, confidence=0.9),
        Keypoint(name="left_hip", x=480.0, y=400.0, confidence=0.9),
        Keypoint(name="right_hip", x=520.0, y=400.0, confidence=0.9),
    ]
    pose_results = [
        PoseEstimationResult(frame_number=0, timestamp=0.0, keypoints=aligned_keypoints),
        PoseEstimationResult(frame_number=1, timestamp=0.1, keypoints=aligned_keypoints),
    ]

    result = calculator.calculate(pose_results, calibrator)

    assert result.posture_score == 100.0


def test_calculate_gives_lower_posture_score_when_misaligned() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    misaligned_keypoints = [
        Keypoint(name="nose", x=560.0, y=100.0, confidence=0.9),  # bien desplazada hacia adelante
        Keypoint(name="left_shoulder", x=480.0, y=200.0, confidence=0.9),
        Keypoint(name="right_shoulder", x=520.0, y=200.0, confidence=0.9),
        Keypoint(name="left_hip", x=480.0, y=400.0, confidence=0.9),
        Keypoint(name="right_hip", x=520.0, y=400.0, confidence=0.9),
    ]
    pose_results = [PoseEstimationResult(frame_number=0, timestamp=0.0, keypoints=misaligned_keypoints)]

    result = calculator.calculate(
        pose_results
        + [PoseEstimationResult(frame_number=1, timestamp=0.1, keypoints=misaligned_keypoints)],
        calibrator,
    )

    assert result.posture_score < 100.0


def test_calculate_handles_missing_calibration_gracefully() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(0.0)  # calibracion invalida

    pose_results = [
        _pose_result(frame_number=i, hip_x=1000 + 20 * i, hip_y=500, ankle_y=700, timestamp=i * 0.1)
        for i in range(5)
    ]

    result = calculator.calculate(pose_results, calibrator)

    # Sin calibracion valida no hay velocidad ni zancada en metros.
    assert result.average_speed == 0.0
    assert result.stride_length == 0.0


def test_calculate_frame_metrics_returns_one_entry_per_frame() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    pose_results = [
        _pose_result(frame_number=i, hip_x=1000 + 20 * i, hip_y=500, ankle_y=700, timestamp=i * 0.1)
        for i in range(5)
    ]

    frame_values = calculator.calculate_frame_metrics(pose_results, calibrator)

    assert [fv.frame_number for fv in frame_values] == [0, 1, 2, 3, 4]
    # El primer cuadro no tiene un cuadro anterior con el cual medir
    # desplazamiento, asi que su velocidad instantanea es 0.
    assert frame_values[0].speed == 0.0
    # Los siguientes sí: misma velocidad constante que en el agregado.
    assert frame_values[1].speed == pytest.approx(2.0, abs=0.01)


def test_calculate_frame_metrics_marks_stride_events_as_apoyo() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    ankle_y_values = [80, 100, 80, 100, 80]
    hip_x_values = [1000, 1010, 1020, 1030, 1040]
    pose_results = [
        _pose_result(
            frame_number=i, hip_x=hip_x_values[i], hip_y=500, ankle_y=ankle_y_values[i], timestamp=i * 0.1
        )
        for i in range(5)
    ]

    frame_values = calculator.calculate_frame_metrics(pose_results, calibrator)
    phases = {fv.frame_number: fv.stride_phase for fv in frame_values}

    assert phases[1] == "apoyo"
    assert phases[3] == "apoyo"
    assert phases[0] == "vuelo"
    assert phases[2] == "vuelo"


def test_calculate_frame_metrics_returns_empty_list_for_no_data() -> None:
    calculator = BasicMetricsCalculator()
    calibrator = _linear_calibrator(100.0)

    assert calculator.calculate_frame_metrics([], calibrator) == []
