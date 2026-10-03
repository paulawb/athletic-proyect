from app.core.exceptions import AthleteNotFoundError
from app.domain.entities.athlete import Athlete
from app.domain.repositories.athlete_repository import AthleteRepository


class GetAthlete:
    def __init__(self, athlete_repository: AthleteRepository) -> None:
        self._athlete_repository = athlete_repository

    async def execute(self, athlete_id: int) -> Athlete:
        athlete = await self._athlete_repository.get_by_id(athlete_id)
        if athlete is None:
            raise AthleteNotFoundError(f"No existe un atleta con id={athlete_id}")
        return athlete
