from abc import ABC, abstractmethod

from app.domain.entities.frame_metrics import FrameMetrics
from app.domain.entities.metrics import Metrics


class MetricsRepository(ABC):
    @abstractmethod
    async def create(self, metrics: Metrics) -> Metrics: ...

    @abstractmethod
    async def get_by_analysis_id(self, analysis_id: int) -> Metrics | None: ...


class FrameMetricsRepository(ABC):
    @abstractmethod
    async def bulk_create(self, frame_metrics: list[FrameMetrics]) -> None:
        """Insercion por lotes; nunca fila por fila (habra cientos de frames)."""
        ...

    @abstractmethod
    async def list_by_analysis_id(self, analysis_id: int) -> list[FrameMetrics]: ...
