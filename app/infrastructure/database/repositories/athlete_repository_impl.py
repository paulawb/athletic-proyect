from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.athlete import Athlete
from app.domain.repositories.athlete_repository import AthleteRepository
from app.infrastructure.database.models.athlete_model import AthleteModel


class SqlAlchemyAthleteRepository(AthleteRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, athlete: Athlete) -> Athlete:
        model = AthleteModel(
            first_name=athlete.first_name,
            last_name=athlete.last_name,
            identification=athlete.identification,
            age=athlete.age,
            gender=athlete.gender,
            email=athlete.email,
            category=athlete.category,
            group_name=athlete.group_name,
            is_active=athlete.is_active,
            owner_user_id=athlete.owner_user_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, athlete_id: int) -> Athlete | None:
        model = await self._session.get(AthleteModel, athlete_id)
        return self._to_entity(model) if model else None

    async def list(self, skip: int = 0, limit: int = 50) -> list[Athlete]:
        result = await self._session.execute(
            select(AthleteModel).order_by(AthleteModel.id).offset(skip).limit(limit)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def update(self, athlete: Athlete) -> Athlete:
        model = await self._session.get(AthleteModel, athlete.id)
        if model is None:
            raise ValueError(f"No existe un atleta con id={athlete.id}")
        model.first_name = athlete.first_name
        model.last_name = athlete.last_name
        model.age = athlete.age
        model.gender = athlete.gender
        model.identification = athlete.identification
        model.email = athlete.email
        model.category = athlete.category
        model.group_name = athlete.group_name
        model.is_active = athlete.is_active
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: AthleteModel) -> Athlete:
        return Athlete(
            id=model.id,
            first_name=model.first_name,
            last_name=model.last_name,
            identification=model.identification,
            age=model.age,
            gender=model.gender,
            email=model.email,
            category=model.category,
            group_name=model.group_name,
            is_active=model.is_active,
            owner_user_id=model.owner_user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
