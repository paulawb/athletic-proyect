from datetime import datetime, timezone

from app.core.timezone import format_local, resolve_timezone


def test_converts_utc_to_selected_timezone():
    value = datetime(2026, 10, 18, 1, 30, tzinfo=timezone.utc)
    assert format_local(value, "America/Bogota") == "17/10/2026 20:30"
    assert format_local(value, "UTC") == "18/10/2026 01:30"


def test_naive_datetimes_are_treated_as_utc():
    assert format_local(datetime(2026, 10, 18, 1, 30), "America/Bogota") == "17/10/2026 20:30"


def test_unknown_timezone_falls_back_to_bogota():
    assert resolve_timezone("No/Existe").key == "America/Bogota"
    assert format_local(None, None) == "-"
