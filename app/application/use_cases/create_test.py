from datetime import datetime, time, timezone

from app.application.dto.test_dto import TestCreateDTO
from app.core.exceptions import AthleteNotFoundError
from app.domain.entities.test import Test
from app.domain.repositories.athlete_repository import AthleteRepository
from app.domain.repositories.test_repository import TestRepository


class CreateTest:
    """Antes de crear la prueba valida que el atleta exista: la integridad
    referencial es una regla de negocio, no algo que deba delegarse solo
    a la foreign key de la base de datos."""

    def __init__(self, test_repository: TestRepository, athlete_repository: AthleteRepository) -> None:
        self._test_repository = test_repository
        self._athlete_repository = athlete_repository

    async def execute(self, data: TestCreateDTO) -> Test:
        athlete = await self._athlete_repository.get_by_id(data.athlete_id)
        if athlete is None:
            raise AthleteNotFoundError(f"No existe un atleta con id={data.athlete_id}")

        test = Test(
            athlete_id=data.athlete_id,
            distance=data.distance,
            test_type=data.test_type,
            technique=data.technique,
            created_at=(
                datetime.combine(data.test_date, time.min, tzinfo=timezone.utc)
                if data.test_date
                else None
            ),
        )
        return await self._test_repository.create(test)
