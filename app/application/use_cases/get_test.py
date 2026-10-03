from app.core.exceptions import TestNotFoundError
from app.domain.entities.test import Test
from app.domain.repositories.test_repository import TestRepository


class GetTest:
    def __init__(self, test_repository: TestRepository) -> None:
        self._test_repository = test_repository

    async def execute(self, test_id: int) -> Test:
        test = await self._test_repository.get_by_id(test_id)
        if test is None:
            raise TestNotFoundError(f"No existe una prueba con id={test_id}")
        return test
