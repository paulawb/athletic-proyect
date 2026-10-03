from app.domain.services.pose_estimator import PoseEstimationResult
from app.infrastructure.vision.mock_pose_estimator import MockPoseEstimator


class _FakeFrame:
    """Doble minimo de np.ndarray: solo necesita exponer .shape."""

    def __init__(self, height: int, width: int) -> None:
        self.shape = (height, width, 3)


def test_estimate_returns_result_with_requested_frame_number() -> None:
    estimator = MockPoseEstimator()

    result = estimator.estimate(_FakeFrame(1080, 1920), frame_number=42)

    assert isinstance(result, PoseEstimationResult)
    assert result.frame_number == 42


def test_estimate_returns_expected_keypoint_set() -> None:
    estimator = MockPoseEstimator()

    result = estimator.estimate(_FakeFrame(1080, 1920), frame_number=0)
    names = {kp.name for kp in result.keypoints}

    assert names == {
        "nose",
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
        "left_hip",
        "right_hip",
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
    }


def test_estimate_keeps_keypoints_within_frame_bounds() -> None:
    estimator = MockPoseEstimator()
    height, width = 1080, 1920

    result = estimator.estimate(_FakeFrame(height, width), frame_number=10)

    for keypoint in result.keypoints:
        assert 0 <= keypoint.x <= width
        assert 0 <= keypoint.y <= height
        assert 0 < keypoint.confidence <= 1


def test_estimate_is_deterministic_for_the_same_frame_number() -> None:
    estimator = MockPoseEstimator()
    frame = _FakeFrame(1080, 1920)

    first = estimator.estimate(frame, frame_number=15)
    second = estimator.estimate(frame, frame_number=15)

    assert first == second


def test_estimate_varies_across_frame_numbers() -> None:
    estimator = MockPoseEstimator()
    frame = _FakeFrame(1080, 1920)

    early = estimator.estimate(frame, frame_number=0)
    later = estimator.estimate(frame, frame_number=15)

    assert early.keypoints != later.keypoints


def test_estimate_falls_back_to_default_resolution_when_frame_has_no_shape() -> None:
    estimator = MockPoseEstimator()

    result = estimator.estimate(None, frame_number=0)

    assert len(result.keypoints) == 13
