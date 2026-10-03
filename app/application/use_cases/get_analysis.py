from app.core.exceptions import AnalysisNotFoundError
from app.domain.entities.analysis import Analysis
from app.domain.repositories.analysis_repository import AnalysisRepository


class GetAnalysis:
    def __init__(self, analysis_repository: AnalysisRepository) -> None:
        self._analysis_repository = analysis_repository

    async def execute(self, analysis_id: int) -> Analysis:
        analysis = await self._analysis_repository.get_by_id(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(f"No existe un analisis con id={analysis_id}")
        return analysis
