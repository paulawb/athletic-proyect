_PREFIX = "ATL-"


def athlete_code(athlete_id: int | None) -> str:
    """Identificador público del atleta. Es lo único que se muestra en pantallas,
    reportes y exportaciones: el nombre solo se captura al registrar."""
    return f"{_PREFIX}{athlete_id:04d}" if athlete_id is not None else "Atleta desconocido"


def athlete_id_from_code(text: str) -> int | None:
    cleaned = text.strip().upper()
    if cleaned.startswith(_PREFIX) and cleaned[len(_PREFIX):].isdigit():
        return int(cleaned[len(_PREFIX):])
    return None
