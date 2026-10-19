from datetime import date, datetime, timezone

from app.application.dto.test_dto import TestCreateDTO
from app.core.exceptions import AthleteNotFoundError
from app.core.timezone import resolve_timezone
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

    async def execute(self, data: TestCreateDTO, timezone_name: str | None = None) -> Test:
        athlete = await self._athlete_repository.get_by_id(data.athlete_id)
        if athlete is None:
            raise AthleteNotFoundError(f"No existe un atleta con id={data.athlete_id}")

        test = Test(
            athlete_id=data.athlete_id,
            distance=data.distance,
            test_type=data.test_type,
            technique=data.technique,
            created_at=self._resolve_moment(data.test_date, timezone_name),
        )
        return await self._test_repository.create(test)

    @staticmethod
    def _resolve_moment(test_date: date | None, timezone_name: str | None) -> datetime | None:
        """La fecha elegida se combina con la hora actual de la zona del usuario
        para que no se corra de día al convertirla desde UTC."""
        if test_date is None:
            return None
        zone = resolve_timezone(timezone_name)
        now_local = datetime.now(zone)
        local = datetime.combine(test_date, now_local.time().replace(microsecond=0), tzinfo=zone)
        return local.astimezone(timezone.utc)
