import pytest

from app.infrastructure.calibration.homography_coordinate_calibrator import HomographyCoordinateCalibrator


def test_from_frame_corners_maps_the_four_corners_correctly() -> None:
    calibrator = HomographyCoordinateCalibrator.from_frame_corners(
        frame_width_px=1920, frame_height_px=1080, reference_distance_m=10.0, lane_width_m=1.22
    )

    assert calibrator.pixel_to_world(0.0, 0.0) == pytest.approx((0.0, 0.0), abs=0.01)
    assert calibrator.pixel_to_world(1920.0, 0.0) == pytest.approx((10.0, 0.0), abs=0.01)
    assert calibrator.pixel_to_world(1920.0, 1080.0) == pytest.approx((10.0, 1.22), abs=0.01)
    assert calibrator.pixel_to_world(0.0, 1080.0) == pytest.approx((0.0, 1.22), abs=0.01)


def test_from_frame_corners_maps_center_to_center() -> None:
    calibrator = HomographyCoordinateCalibrator.from_frame_corners(
        frame_width_px=1920, frame_height_px=1080, reference_distance_m=10.0, lane_width_m=1.22
    )

    x_m, y_m = calibrator.pixel_to_world(960.0, 540.0)

    assert x_m == pytest.approx(5.0, abs=0.01)
    assert y_m == pytest.approx(0.61, abs=0.01)


def test_corrects_perspective_with_a_trapezoidal_source() -> None:
    # Simula una vista con perspectiva: el lado "lejano" (y_px chico) se ve
    # mas angosto en pixeles que el lado "cercano" (y_px grande), aunque en
    # el mundo real el carril mide lo mismo de ancho en ambos extremos.
    pixel_points = [
        (400.0, 0.0),  # inicio, lado lejano
        (1600.0, 0.0),  # fin, lado lejano (se ve angosto)
        (1800.0, 1000.0),  # fin, lado cercano (se ve mas ancho)
        (200.0, 1000.0),  # inicio, lado cercano
    ]
    world_points = [(0.0, 0.0), (10.0, 0.0), (10.0, 1.22), (0.0, 1.22)]
    calibrator = HomographyCoordinateCalibrator(pixel_points, world_points)

    # Ambos lados tienen su punto medio en x_px=1000 (trapecio simetrico);
    # deberian mapear al mismo x=5.0 en el mundo real -eso es justamente lo
    # que corrige la homografia, algo que una escala lineal no podria hacer.
    x_far, y_far = calibrator.pixel_to_world(1000.0, 0.0)
    x_near, y_near = calibrator.pixel_to_world(1000.0, 1000.0)

    assert x_far == pytest.approx(5.0, abs=0.5)
    assert x_near == pytest.approx(5.0, abs=0.5)
    assert y_far == pytest.approx(0.0, abs=0.05)
    assert y_near == pytest.approx(1.22, abs=0.05)


def test_constructor_requires_exactly_four_points() -> None:
    with pytest.raises(ValueError):
        HomographyCoordinateCalibrator(
            pixel_points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)],
            world_points=[(0.0, 0.0), (10.0, 0.0), (10.0, 1.0)],
        )
