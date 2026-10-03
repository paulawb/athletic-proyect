from app.domain.entities.test import Test
from app.domain.repositories.test_repository import TestRepository


class ListTests:
    def __init__(self, test_repository: TestRepository) -> None:
        self._test_repository = test_repository

    async def execute(self, athlete_id: int | None = None, skip: int = 0, limit: int = 50) -> list[Test]:
        if athlete_id is not None:
            return await self._test_repository.list_by_athlete(athlete_id)
        return await self._test_repository.list(skip=skip, limit=limit)
