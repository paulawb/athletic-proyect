from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.application.dto.test_dto import TestCreateDTO
from app.application.use_cases.create_test import CreateTest
from app.application.use_cases.list_tests import ListTests
from app.core.exceptions import AthleteNotFoundError
from app.domain.entities.athlete import Athlete
from app.domain.entities.test import Test
from app.domain.repositories.athlete_repository import AthleteRepository
from app.domain.repositories.test_repository import TestRepository


class FakeAthleteRepository(AthleteRepository):
    def __init__(self, athletes: list[Athlete] | None = None) -> None:
        self._athletes = {a.id: a for a in (athletes or [])}

    async def create(self, athlete: Athlete) -> Athlete:
        self._athletes[athlete.id] = athlete
        return athlete

    async def get_by_id(self, athlete_id: int) -> Athlete | None:
        return self._athletes.get(athlete_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Athlete]:
        return list(self._athletes.values())[skip : skip + limit]

    async def update(self, athlete: Athlete) -> Athlete:
        self._athletes[athlete.id] = athlete
        return athlete


class FakeTestRepository(TestRepository):
    def __init__(self) -> None:
        self._tests: dict[int, Test] = {}
        self._next_id = 1

    async def create(self, test: Test) -> Test:
        test.id = self._next_id
        self._tests[test.id] = test
        self._next_id += 1
        return test

    async def get_by_id(self, test_id: int) -> Test | None:
        return self._tests.get(test_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Test]:
        return list(self._tests.values())[skip : skip + limit]

    async def list_by_athlete(self, athlete_id: int) -> list[Test]:
        return [t for t in self._tests.values() if t.athlete_id == athlete_id]

    async def update_status(self, test_id: int, status: str) -> Test:
        test = self._tests[test_id]
        test.status = status
        return test


def _existing_athlete() -> Athlete:
    return Athlete(id=1, first_name="Juan", last_name="Pérez", identification="100123456", age=17, gender="M")


def _create_dto(**overrides) -> TestCreateDTO:
    base = dict(athlete_id=1, distance=10, test_type="Carrera de velocidad", technique="Salida de tacos")
    base.update(overrides)
    return TestCreateDTO(**base)


async def test_create_test_succeeds_when_athlete_exists() -> None:
    athlete_repository = FakeAthleteRepository([_existing_athlete()])
    test_repository = FakeTestRepository()

    test = await CreateTest(test_repository, athlete_repository).execute(_create_dto())

    assert test.id == 1
    assert test.athlete_id == 1
    assert test.status.value == "PENDING"


async def test_create_test_keeps_the_requested_test_date() -> None:
    athlete_repository = FakeAthleteRepository([_existing_athlete()])
    test_repository = FakeTestRepository()

    test = await CreateTest(test_repository, athlete_repository).execute(_create_dto(test_date=date(2025, 4, 12)))

    assert test.created_at == datetime(2025, 4, 12, tzinfo=timezone.utc)


async def test_create_test_raises_when_athlete_does_not_exist() -> None:
    athlete_repository = FakeAthleteRepository([])
    test_repository = FakeTestRepository()

    with pytest.raises(AthleteNotFoundError):
        await CreateTest(test_repository, athlete_repository).execute(_create_dto(athlete_id=99))


async def test_list_tests_filters_by_athlete_when_requested() -> None:
    athlete_repository = FakeAthleteRepository([_existing_athlete(), Athlete(id=2, first_name="Laura", last_name="Gómez", identification="100654321", age=16, gender="F")])
    test_repository = FakeTestRepository()
    await CreateTest(test_repository, athlete_repository).execute(_create_dto(athlete_id=1))
    await CreateTest(test_repository, athlete_repository).execute(_create_dto(athlete_id=2))

    all_tests = await ListTests(test_repository).execute()
    athlete_1_tests = await ListTests(test_repository).execute(athlete_id=1)

    assert len(all_tests) == 2
    assert len(athlete_1_tests) == 1
    assert athlete_1_tests[0].athlete_id == 1
