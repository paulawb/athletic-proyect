from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.tasks.processing_queue import waiting_analysis_ids

STALE_MESSAGE = (
    "El procesamiento se interrumpió (el servidor se reinició o tardó demasiado). "
    "Elimina este análisis y vuelve a intentarlo con un video más corto o de menor resolución."
)


async def fail_stale_analyses(session: AsyncSession, max_idle_minutes: float | None = None) -> int:
    """Marca como FAILED los analisis que nadie esta procesando ya.

    El procesamiento corre en el mismo proceso que la API: si el servidor se
    reinicia o el hilo muere, el analisis quedaria en PENDING/PROCESSING para
    siempre. started_at se renueva con cada reporte de progreso, asi que sirve
    como latido. Los analisis que este proceso tiene en cola esperando turno
    (ver processing_queue) no estan atascados y se excluyen."""
    if max_idle_minutes is None:
        max_idle_minutes = get_settings().analysis_stale_minutes
    limit = datetime.now(timezone.utc) - timedelta(minutes=max_idle_minutes)
    statement = update(AnalysisModel).where(
        func.upper(AnalysisModel.status).in_(("PENDING", "PROCESSING")),
        func.coalesce(AnalysisModel.started_at, AnalysisModel.created_at) < limit,
    )
    waiting = waiting_analysis_ids()
    if waiting:
        statement = statement.where(AnalysisModel.id.notin_(sorted(waiting)))
    result = await session.execute(
        statement.values(status="FAILED", error_message=STALE_MESSAGE, completed_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return result.rowcount or 0
