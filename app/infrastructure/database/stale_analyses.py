from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.analysis_model import AnalysisModel

STALE_MESSAGE = (
    "El procesamiento se interrumpió (el servidor se reinició o tardó demasiado). "
    "Elimina este análisis y vuelve a intentarlo con un video más corto o de menor resolución."
)


async def fail_stale_analyses(session: AsyncSession, max_idle_minutes: float = 5) -> int:
    """Marca como FAILED los analisis que nadie esta procesando ya.

    El procesamiento corre en el mismo proceso que la API: si el servidor se
    reinicia o el hilo muere, el analisis quedaria en PENDING/PROCESSING para
    siempre. started_at se renueva con cada reporte de progreso, asi que sirve
    como latido."""
    limit = datetime.now(timezone.utc) - timedelta(minutes=max_idle_minutes)
    result = await session.execute(
        update(AnalysisModel)
        .where(
            func.upper(AnalysisModel.status).in_(("PENDING", "PROCESSING")),
            func.coalesce(AnalysisModel.started_at, AnalysisModel.created_at) < limit,
        )
        .values(status="FAILED", error_message=STALE_MESSAGE, completed_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return result.rowcount or 0
