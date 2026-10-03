import pytest

from app.domain.services.metrics_calculator import CameraCalibration
from app.infrastructure.calibration.linear_coordinate_calibrator import LinearCoordinateCalibrator


def test_pixel_to_world_scales_by_pixels_per_meter() -> None:
    calibrator = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=100.0))

    x_m, y_m = calibrator.pixel_to_world(200.0, 300.0)

    assert x_m == pytest.approx(2.0)
    assert y_m == pytest.approx(3.0)


def test_pixel_to_world_raises_for_invalid_calibration() -> None:
    calibrator = LinearCoordinateCalibrator(CameraCalibration(pixels_per_meter=0.0))

    with pytest.raises(ValueError):
        calibrator.pixel_to_world(100.0, 100.0)
