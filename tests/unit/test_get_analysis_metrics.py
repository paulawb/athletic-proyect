from __future__ import annotations

import pytest

from app.application.use_cases.get_analysis_metrics import GetAnalysisMetrics
from app.core.exceptions import AnalysisNotFoundError, MetricsNotFoundError
from app.domain.entities.analysis import Analysis, AnalysisStatus
from app.domain.entities.metrics import Metrics
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.metrics_repository import MetricsRepository


class FakeAnalysisRepository(AnalysisRepository):
    def __init__(self, analyses: list[Analysis] | None = None) -> None:
        self._analyses = {a.id: a for a in (analyses or [])}

    async def create(self, analysis: Analysis) -> Analysis:
        self._analyses[analysis.id] = analysis
        return analysis

    async def get_by_id(self, analysis_id: int) -> Analysis | None:
        return self._analyses.get(analysis_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Analysis]:
        return list(self._analyses.values())[skip : skip + limit]

    async def list_by_video_id(self, video_id: int) -> list[Analysis]:
        return [a for a in self._analyses.values() if a.video_id == video_id]

    async def update_progress(self, analysis_id, status, processed_frames, error_message=None) -> Analysis:
        analysis = self._analyses[analysis_id]
        analysis.status = status
        return analysis

    async def update_progress_batch(self, analysis_id: int, processed_frames: int) -> None:
        raise NotImplementedError("no se usa en estas pruebas")


class FakeMetricsRepository(MetricsRepository):
    def __init__(self, metrics: list[Metrics] | None = None) -> None:
        self._metrics = metrics or []

    async def create(self, metrics: Metrics) -> Metrics:
        self._metrics.append(metrics)
        return metrics

    async def get_by_analysis_id(self, analysis_id: int) -> Metrics | None:
        return next((m for m in self._metrics if m.analysis_id == analysis_id), None)


def _completed_analysis(analysis_id: int = 1) -> Analysis:
    return Analysis(id=analysis_id, video_id=1, status=AnalysisStatus.COMPLETED, processed_frames=45, total_frames=45)


def _metrics(analysis_id: int = 1) -> Metrics:
    return Metrics(
        analysis_id=analysis_id,
        average_speed=7.18,
        maximum_speed=8.42,
        stride_length=1.82,
        cadence=4.21,
        posture_score=87.5,
    )


async def test_get_analysis_metrics_returns_persisted_metrics() -> None:
    use_case = GetAnalysisMetrics(
        analysis_repository=FakeAnalysisRepository([_completed_analysis()]),
        metrics_repository=FakeMetricsRepository([_metrics()]),
    )

    metrics = await use_case.execute(analysis_id=1)

    assert metrics.average_speed == 7.18
    assert metrics.cadence == 4.21


async def test_get_analysis_metrics_raises_when_analysis_does_not_exist() -> None:
    use_case = GetAnalysisMetrics(
        analysis_repository=FakeAnalysisRepository([]), metrics_repository=FakeMetricsRepository([])
    )

    with pytest.raises(AnalysisNotFoundError):
        await use_case.execute(analysis_id=999)


async def test_get_analysis_metrics_raises_when_metrics_not_yet_computed() -> None:
    use_case = GetAnalysisMetrics(
        analysis_repository=FakeAnalysisRepository([_completed_analysis()]),
        metrics_repository=FakeMetricsRepository([]),
    )

    with pytest.raises(MetricsNotFoundError):
        await use_case.execute(analysis_id=1)
