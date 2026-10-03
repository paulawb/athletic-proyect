import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    # Evita registrar cuerpos de request/response completos, que podrian
    # contener datos personales de atletas.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


logger = logging.getLogger("athletic_analysis")
