from app.domain.services.pose_estimator import Keypoint, PoseEstimationResult
from app.domain.services.trajectory_calibration import calibrate_to_trajectory
from app.infrastructure.calibration.linear_coordinate_calibrator import LinearCoordinateCalibrator
from app.domain.services.metrics_calculator import CameraCalibration


def _pose(frame: int, hip_x: float) -> PoseEstimationResult:
    return PoseEstimationResult(
        frame_number=frame,
        timestamp=frame / 30,
        keypoints=[
            Keypoint(name="left_hip", x=hip_x, y=500, confidence=0.9),
            Keypoint(name="right_hip", x=hip_x, y=500, confidence=0.9),
        ],
    )


def test_trajectory_calibration_makes_run_match_test_distance():
    # El encuadre mide 1000 px y se supone 10 m, pero la cadera recorre 800 px.
    poses = [_pose(i, 100 + i * 8) for i in range(101)]
    base = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=100.0, reference_distance_m=10.0))

    calibrator = calibrate_to_trajectory(poses, base, 10.0)

    start = calibrator.pixel_to_world(100, 0)[0]
    end = calibrator.pixel_to_world(900, 0)[0]
    # La mediana de los extremos recorta ~2 cuadros, de ahí la tolerancia.
    assert abs((end - start) - 10.0) < 0.3


def test_trajectory_calibration_keeps_scale_when_movement_is_implausible():
    poses = [_pose(i, 500 + i * 0.1) for i in range(101)]
    base = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=100.0, reference_distance_m=10.0))

    assert calibrate_to_trajectory(poses, base, 10.0) is base
