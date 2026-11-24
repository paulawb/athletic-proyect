import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# El plan gratuito de Render tiene 512 MB de RAM: dos videos procesandose a la
# vez cargan dos modelos de pose y varios cuadros en memoria, y el servicio se
# reinicia por falta de memoria. Por eso se procesa un solo video a la vez; los
# demas esperan su turno en PENDING.
_processing_lock = asyncio.Lock()
_waiting_ids: set[int] = set()


def waiting_analysis_ids() -> frozenset[int]:
    """Analisis que este proceso tiene en cola esperando su turno. No estan
    atascados aunque lleven tiempo en PENDING, asi que fail_stale_analyses
    no debe marcarlos como fallidos."""
    return frozenset(_waiting_ids)


async def run_one_at_a_time(analysis_id: int, job: Callable[[], Awaitable[object]]) -> None:
    _waiting_ids.add(analysis_id)
    try:
        async with _processing_lock:
            _waiting_ids.discard(analysis_id)
            await job()
    except Exception:
        logger.exception("Fallo inesperado al procesar el analisis id=%s", analysis_id)
    finally:
        _waiting_ids.discard(analysis_id)
