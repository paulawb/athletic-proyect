from types import SimpleNamespace

import pytest

from app.domain.services.pose_estimator import KeypointName
from app.infrastructure.vision.mediapipe_pose_estimator import (
    _LANDMARK_INDEX,
    MediaPipePoseEstimator,
    _extract_valid_keypoints,
)


def _running_pose(confidence: float = 0.9) -> list[SimpleNamespace]:
    landmarks = [
        SimpleNamespace(x=0.5, y=0.5, visibility=confidence, presence=confidence)
        for _ in range(33)
    ]
    positions = {
        KeypointName.NOSE: (0.5, 0.15),
        KeypointName.LEFT_SHOULDER: (0.45, 0.25),
        KeypointName.RIGHT_SHOULDER: (0.55, 0.25),
        KeypointName.LEFT_HIP: (0.47, 0.5),
        KeypointName.RIGHT_HIP: (0.53, 0.5),
        KeypointName.LEFT_KNEE: (0.4, 0.7),
        KeypointName.RIGHT_KNEE: (0.6, 0.65),
        KeypointName.LEFT_ANKLE: (0.35, 0.9),
        KeypointName.RIGHT_ANKLE: (0.65, 0.82),
    }
    for name, (x, y) in positions.items():
        landmarks[_LANDMARK_INDEX[name]] = SimpleNamespace(
            x=x, y=y, visibility=confidence, presence=confidence
        )
    return landmarks


def test_raises_clear_error_when_model_file_is_missing(tmp_path) -> None:
    missing_path = tmp_path / "no-existe.task"

    with pytest.raises(FileNotFoundError, match="No se encontro el modelo"):
        MediaPipePoseEstimator(model_path=str(missing_path))


def test_landmark_index_covers_every_keypoint_name() -> None:
    """Si alguien agrega un KeypointName nuevo sin mapear su indice de
    MediaPipe aca, BasicMetricsCalculator buscaria ese punto y nunca lo
    encontraria -en silencio. Esta prueba lo detecta antes de eso."""
    assert set(_LANDMARK_INDEX.keys()) == set(KeypointName)


def test_landmark_index_values_are_within_mediapipes_33_landmarks() -> None:
    assert all(0 <= index <= 32 for index in _LANDMARK_INDEX.values())


def test_landmark_index_has_no_duplicate_indices() -> None:
    indices = list(_LANDMARK_INDEX.values())
    assert len(indices) == len(set(indices))


def test_extracts_confident_anatomically_plausible_running_pose() -> None:
    keypoints = _extract_valid_keypoints(_running_pose(), width=640, height=480)

    assert len(keypoints) == len(_LANDMARK_INDEX)
    assert {keypoint.name for keypoint in keypoints} == {name.value for name in KeypointName}


def test_rejects_pose_without_confident_torso_landmarks() -> None:
    landmarks = _running_pose()
    landmarks[_LANDMARK_INDEX[KeypointName.LEFT_SHOULDER]].visibility = 0.2
    landmarks[_LANDMARK_INDEX[KeypointName.RIGHT_SHOULDER]].visibility = 0.2

    assert _extract_valid_keypoints(landmarks, width=640, height=480) == []


def test_rejects_pose_with_implausible_torso_geometry() -> None:
    landmarks = _running_pose()
    for name in (KeypointName.LEFT_HIP, KeypointName.RIGHT_HIP):
        landmarks[_LANDMARK_INDEX[name]].y = 0.2

    assert _extract_valid_keypoints(landmarks, width=640, height=480) == []


def test_uses_presence_when_visibility_is_not_available() -> None:
    landmarks = _running_pose()
    for landmark in landmarks:
        landmark.visibility = None

    keypoints = _extract_valid_keypoints(landmarks, width=640, height=480)

    assert len(keypoints) == len(_LANDMARK_INDEX)
