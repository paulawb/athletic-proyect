from __future__ import annotations

import pytest

from app.application.dto.athlete_dto import AthleteCreateDTO
from app.application.use_cases.create_athlete import CreateAthlete
from app.application.use_cases.get_athlete import GetAthlete
from app.application.use_cases.list_athletes import ListAthletes
from app.core.exceptions import AthleteNotFoundError
from app.domain.entities.athlete import Athlete
from app.domain.repositories.athlete_repository import AthleteRepository


class FakeAthleteRepository(AthleteRepository):
    def __init__(self) -> None:
        self._athletes: dict[int, Athlete] = {}
        self._next_id = 1

    async def create(self, athlete: Athlete) -> Athlete:
        athlete.id = self._next_id
        self._athletes[athlete.id] = athlete
        self._next_id += 1
        return athlete

    async def get_by_id(self, athlete_id: int) -> Athlete | None:
        return self._athletes.get(athlete_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Athlete]:
        return list(self._athletes.values())[skip : skip + limit]

    async def update(self, athlete: Athlete) -> Athlete:
        self._athletes[athlete.id] = athlete
        return athlete


def _create_dto(**overrides) -> AthleteCreateDTO:
    base = dict(first_name="Juan", last_name="Pérez", identification="100123456", age=17, gender="M")
    base.update(overrides)
    return AthleteCreateDTO(**base)


async def test_create_athlete_persists_and_returns_entity() -> None:
    repository = FakeAthleteRepository()

    athlete = await CreateAthlete(repository).execute(_create_dto())

    assert athlete.id == 1
    assert athlete.first_name == "Juan"


async def test_get_athlete_returns_existing_athlete() -> None:
    repository = FakeAthleteRepository()
    created = await CreateAthlete(repository).execute(_create_dto())

    found = await GetAthlete(repository).execute(created.id)

    assert found.identification == "100123456"


async def test_get_athlete_raises_when_not_found() -> None:
    repository = FakeAthleteRepository()

    with pytest.raises(AthleteNotFoundError):
        await GetAthlete(repository).execute(999)


async def test_list_athletes_returns_created_athletes() -> None:
    repository = FakeAthleteRepository()
    await CreateAthlete(repository).execute(_create_dto())
    await CreateAthlete(repository).execute(_create_dto(first_name="Laura", identification="100654321"))

    athletes = await ListAthletes(repository).execute()

    assert len(athletes) == 2
    assert {a.first_name for a in athletes} == {"Juan", "Laura"}
