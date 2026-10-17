from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "America/Bogota"


def resolve_timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def to_local(value: datetime | None, name: str | None) -> datetime | None:
    """Convierte una marca de tiempo guardada en UTC a la zona horaria elegida.
    Las fechas sin zona se interpretan como UTC, que es como las guarda la BD."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(resolve_timezone(name))


def format_local(value: datetime | None, name: str | None, pattern: str = "%d/%m/%Y %H:%M") -> str:
    local = to_local(value, name)
    return local.strftime(pattern) if local else "-"
