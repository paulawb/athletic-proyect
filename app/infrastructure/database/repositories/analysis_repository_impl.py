from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.analysis import Analysis, AnalysisStatus
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.infrastructure.database.models.analysis_model import AnalysisModel


class SqlAlchemyAnalysisRepository(AnalysisRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, analysis: Analysis) -> Analysis:
        model = AnalysisModel(
            video_id=analysis.video_id,
            status=analysis.status.value,
            processed_frames=analysis.processed_frames,
            total_frames=analysis.total_frames,
            started_at=analysis.started_at,
            completed_at=analysis.completed_at,
            error_message=analysis.error_message,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, analysis_id: int) -> Analysis | None:
        model = await self._session.get(AnalysisModel, analysis_id)
        return self._to_entity(model) if model else None

    async def list(self, skip: int = 0, limit: int = 50) -> list[Analysis]:
        result = await self._session.execute(
            select(AnalysisModel).order_by(AnalysisModel.id.desc()).offset(skip).limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_by_video_id(self, video_id: int) -> list[Analysis]:
        result = await self._session.execute(
            select(AnalysisModel)
            .where(AnalysisModel.video_id == video_id)
            .order_by(AnalysisModel.id.desc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def update_progress(
        self,
        analysis_id: int,
        status: AnalysisStatus,
        processed_frames: int,
        error_message: str | None = None,
    ) -> Analysis:
        """UPDATE + RETURNING: una sola query sin SELECT previo.

        La version anterior hacia session.get() (SELECT) antes del UPDATE,
        lo que duplicaba la query por cada reporte de progreso (cada 10
        cuadros). Con RETURNING obtenemos el registro actualizado en la
        misma query que el UPDATE, sin el SELECT adicional.
        """
        now = datetime.now(timezone.utc)
        values: dict = {
            "status": status.value,
            "processed_frames": processed_frames,
        }
        if error_message is not None:
            values["error_message"] = error_message
        if status == AnalysisStatus.PROCESSING:
            values["started_at"] = now
        if status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
            values["completed_at"] = now

        result = await self._session.execute(
            update(AnalysisModel)
            .where(AnalysisModel.id == analysis_id)
            .values(**values)
            .returning(AnalysisModel)
        )
        try:
            model = result.scalar_one()
        except NoResultFound as exc:
            raise ValueError(f"No existe un analisis con id={analysis_id}") from exc

        await self._session.commit()
        return self._to_entity(model)

    async def update_progress_batch(self, analysis_id: int, processed_frames: int) -> None:
        """UPDATE liviano: solo actualiza processed_frames, sin SELECT ni
        RETURNING. Se usa dentro del loop de cuadros (cada 10) para no
        pagarse un SELECT+UPDATE+RETURNING por cada reporte de progreso.
        El cambio de estado a COMPLETED/FAILED llega por update_progress
        al terminar, que sí necesita el registro completo."""
        await self._session.execute(
            update(AnalysisModel)
            .where(AnalysisModel.id == analysis_id)
            .values(processed_frames=processed_frames)
        )
        await self._session.commit()

    @staticmethod
    def _to_entity(model: AnalysisModel) -> Analysis:
        return Analysis(
            id=model.id,
            video_id=model.video_id,
            status=AnalysisStatus(model.status),
            processed_frames=model.processed_frames,
            total_frames=model.total_frames,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            created_at=model.created_at,
        )
