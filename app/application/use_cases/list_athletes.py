from app.domain.entities.athlete import Athlete
from app.domain.repositories.athlete_repository import AthleteRepository


class ListAthletes:
    def __init__(self, athlete_repository: AthleteRepository) -> None:
        self._athlete_repository = athlete_repository

    async def execute(self, skip: int = 0, limit: int = 50) -> list[Athlete]:
        return await self._athlete_repository.list(skip=skip, limit=limit)
