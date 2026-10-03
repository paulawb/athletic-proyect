from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.test import Test


class TestRepository(ABC):
    @abstractmethod
    async def create(self, test: Test) -> Test: ...

    @abstractmethod
    async def get_by_id(self, test_id: int) -> Test | None: ...

    @abstractmethod
    async def list(self, skip: int = 0, limit: int = 50) -> list[Test]:
        """Listado general (GET /api/v1/pruebas), sin filtrar por atleta."""
        ...

    @abstractmethod
    async def list_by_athlete(self, athlete_id: int) -> list[Test]: ...

    @abstractmethod
    async def update_status(self, test_id: int, status: str) -> Test: ...
