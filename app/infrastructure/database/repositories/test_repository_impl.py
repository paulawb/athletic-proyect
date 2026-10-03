from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.test import Test, TestStatus
from app.domain.repositories.test_repository import TestRepository
from app.infrastructure.database.models.test_model import TestModel


class SqlAlchemyTestRepository(TestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, test: Test) -> Test:
        model = TestModel(
            athlete_id=test.athlete_id,
            distance=test.distance,
            test_type=test.test_type,
            technique=test.technique,
            status=test.status.value,
            created_at=test.created_at,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, test_id: int) -> Test | None:
        model = await self._session.get(TestModel, test_id)
        return self._to_entity(model) if model else None

    async def list(self, skip: int = 0, limit: int = 50) -> list[Test]:
        result = await self._session.execute(
            select(TestModel).order_by(TestModel.id.desc()).offset(skip).limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_by_athlete(self, athlete_id: int) -> list[Test]:
        result = await self._session.execute(
            select(TestModel).where(TestModel.athlete_id == athlete_id).order_by(TestModel.id.desc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def update_status(self, test_id: int, status: str) -> Test:
        model = await self._session.get(TestModel, test_id)
        if model is None:
            raise ValueError(f"No existe una prueba con id={test_id}")
        model.status = status
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: TestModel) -> Test:
        return Test(
            id=model.id,
            athlete_id=model.athlete_id,
            distance=model.distance,
            test_type=model.test_type,
            technique=model.technique,
            status=TestStatus(model.status),
            created_at=model.created_at,
        )
