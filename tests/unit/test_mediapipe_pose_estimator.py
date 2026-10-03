import pytest

from app.domain.services.pose_estimator import KeypointName
from app.infrastructure.vision.mediapipe_pose_estimator import _LANDMARK_INDEX, MediaPipePoseEstimator


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
