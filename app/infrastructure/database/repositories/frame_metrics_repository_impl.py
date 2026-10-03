from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.frame_metrics import FrameMetrics
from app.domain.repositories.metrics_repository import FrameMetricsRepository
from app.infrastructure.database.models.frame_metrics_model import FrameMetricsModel


class SqlAlchemyFrameMetricsRepository(FrameMetricsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, frame_metrics: list[FrameMetrics]) -> None:
        if not frame_metrics:
            return
        # Insercion por lotes (una sola sesion/commit para todos los cuadros),
        # nunca fila por fila: habra cientos de FrameMetrics por analisis.
        models = [
            FrameMetricsModel(
                analysis_id=fm.analysis_id,
                frame_number=fm.frame_number,
                timestamp=fm.timestamp,
                x_position=fm.x_position,
                y_position=fm.y_position,
                speed=fm.speed,
                stride_phase=fm.stride_phase,
                posture_score=fm.posture_score,
                keypoints=fm.keypoints,
            )
            for fm in frame_metrics
        ]
        self._session.add_all(models)
        await self._session.commit()

    async def list_by_analysis_id(self, analysis_id: int) -> list[FrameMetrics]:
        result = await self._session.execute(
            select(FrameMetricsModel)
            .where(FrameMetricsModel.analysis_id == analysis_id)
            .order_by(FrameMetricsModel.frame_number)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    @staticmethod
    def _to_entity(model: FrameMetricsModel) -> FrameMetrics:
        return FrameMetrics(
            id=model.id,
            analysis_id=model.analysis_id,
            frame_number=model.frame_number,
            timestamp=model.timestamp,
            x_position=model.x_position,
            y_position=model.y_position,
            speed=model.speed,
            stride_phase=model.stride_phase,
            posture_score=model.posture_score,
            keypoints=model.keypoints,
        )
