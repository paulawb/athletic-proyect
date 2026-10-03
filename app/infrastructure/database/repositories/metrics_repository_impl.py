from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.metrics import Metrics
from app.domain.repositories.metrics_repository import MetricsRepository
from app.infrastructure.database.models.metrics_model import MetricsModel


class SqlAlchemyMetricsRepository(MetricsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, metrics: Metrics) -> Metrics:
        model = MetricsModel(
            analysis_id=metrics.analysis_id,
            average_speed=metrics.average_speed,
            maximum_speed=metrics.maximum_speed,
            stride_length=metrics.stride_length,
            cadence=metrics.cadence,
            posture_score=metrics.posture_score,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_analysis_id(self, analysis_id: int) -> Metrics | None:
        result = await self._session.execute(
            select(MetricsModel).where(MetricsModel.analysis_id == analysis_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    @staticmethod
    def _to_entity(model: MetricsModel) -> Metrics:
        return Metrics(
            id=model.id,
            analysis_id=model.analysis_id,
            average_speed=model.average_speed,
            maximum_speed=model.maximum_speed,
            stride_length=model.stride_length,
            cadence=model.cadence,
            posture_score=model.posture_score,
            created_at=model.created_at,
        )
