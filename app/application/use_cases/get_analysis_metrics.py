from app.core.exceptions import AnalysisNotFoundError, MetricsNotFoundError
from app.domain.entities.metrics import Metrics
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.metrics_repository import MetricsRepository


class GetAnalysisMetrics:
    def __init__(self, analysis_repository: AnalysisRepository, metrics_repository: MetricsRepository) -> None:
        self._analysis_repository = analysis_repository
        self._metrics_repository = metrics_repository

    async def execute(self, analysis_id: int) -> Metrics:
        analysis = await self._analysis_repository.get_by_id(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(f"No existe un analisis con id={analysis_id}")

        metrics = await self._metrics_repository.get_by_analysis_id(analysis_id)
        if metrics is None:
            raise MetricsNotFoundError(
                f"El analisis id={analysis_id} todavia no tiene metricas "
                f"(estado actual: {analysis.status.value})"
            )
        return metrics
