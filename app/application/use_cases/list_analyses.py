from app.domain.entities.analysis import Analysis
from app.domain.repositories.analysis_repository import AnalysisRepository


class ListAnalyses:
    def __init__(self, analysis_repository: AnalysisRepository) -> None:
        self._analysis_repository = analysis_repository

    async def execute(self, skip: int = 0, limit: int = 50) -> list[Analysis]:
        return await self._analysis_repository.list(skip=skip, limit=limit)
