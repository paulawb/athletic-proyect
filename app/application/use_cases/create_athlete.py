from app.application.dto.athlete_dto import AthleteCreateDTO
from app.domain.entities.athlete import Athlete
from app.domain.repositories.athlete_repository import AthleteRepository


class CreateAthlete:
    def __init__(self, athlete_repository: AthleteRepository) -> None:
        self._athlete_repository = athlete_repository

    async def execute(self, data: AthleteCreateDTO) -> Athlete:
        athlete = Athlete(
            first_name=data.first_name,
            last_name=data.last_name,
            identification=data.identification,
            age=data.age,
            gender=data.gender,
            email=data.email,
            category=data.category,
            group_name=data.group_name,
        )
        return await self._athlete_repository.create(athlete)
