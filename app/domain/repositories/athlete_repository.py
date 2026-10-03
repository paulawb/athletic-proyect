from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.athlete import Athlete


class AthleteRepository(ABC):
    @abstractmethod
    async def create(self, athlete: Athlete) -> Athlete: ...

    @abstractmethod
    async def get_by_id(self, athlete_id: int) -> Athlete | None: ...

    @abstractmethod
    async def list(self, skip: int = 0, limit: int = 50) -> list[Athlete]: ...

    @abstractmethod
    async def update(self, athlete: Athlete) -> Athlete: ...
