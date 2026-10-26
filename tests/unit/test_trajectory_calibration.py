from app.domain.services.pose_estimator import Keypoint, PoseEstimationResult
from app.domain.services.trajectory_calibration import (
    calibrate_to_trajectory,
    run_duration_seconds,
    simulate_tracking_camera_progress,
)
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



def test_tracking_camera_progress_gives_distance_over_time():
    # Cámara en seguimiento: la cadera queda quieta en píxeles durante 4 s.
    poses = [_pose(i, 500) for i in range(121)]
    base = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=100.0, reference_distance_m=40.0))

    shifted = simulate_tracking_camera_progress(poses, base, 40.0)

    first = shifted[0].keypoints[0].x
    last = shifted[-1].keypoints[0].x
    assert round((last - first) / 100.0, 2) == 40.0
    assert poses[-1].keypoints[0].x == 500


def test_tracking_camera_with_run_window_ignores_time_outside_it():
    poses = [_pose(i, 500) for i in range(121)]  # 4 s a 30 fps
    base = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=100.0, reference_distance_m=40.0))

    shifted = simulate_tracking_camera_progress(poses, base, 40.0, run_window=(1.0, 3.0))

    xs = [r.keypoints[0].x for r in shifted]
    assert xs[0] == xs[30] == 500
    assert round((xs[90] - xs[30]) / 100.0, 2) == 40.0
    assert xs[-1] == xs[90]


def test_run_duration_uses_marked_window_first():
    poses = [_pose(i, 100 + i * 8) for i in range(101)]

    assert run_duration_seconds(poses, (0.5, 3.0), True) == 2.5


def test_run_duration_uses_trajectory_extremes_for_fixed_camera():
    # Parado 1 s, corre 2,5 s y se detiene: 10 m en 2,5 s, no en todo el video.
    poses = [_pose(i, 100) for i in range(30)]
    poses += [_pose(30 + i, 100 + i * 10) for i in range(76)]
    poses += [_pose(106 + i, 850) for i in range(30)]

    duration = run_duration_seconds(poses, None, True)

    assert duration is not None and abs(duration - 2.5) < 0.2


def test_trajectory_calibration_keeps_scale_when_movement_is_implausible():
    poses = [_pose(i, 500 + i * 0.1) for i in range(101)]
    base = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=100.0, reference_distance_m=10.0))

    assert calibrate_to_trajectory(poses, base, 10.0) is base
