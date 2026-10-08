from datetime import datetime, timezone

import pytest

from app.domain.entities.user import User
from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.database.models.athlete_model import AthleteModel
from app.infrastructure.database.models.metrics_model import MetricsModel
from app.infrastructure.database.models.test_model import TestModel
from app.presentation.api.v1.routes import workspace


class QueryResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class ReportSession:
    def __init__(self, rows=(), report=None) -> None:
        self.rows = rows
        self.report = report
        self.added = None
        self.commits = 0

    async def execute(self, _query):
        return QueryResult(self.rows)

    async def scalar(self, _query):
        return self.report

    def add(self, item) -> None:
        self.added = item

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _item) -> None:
        return None


def _report_row():
    analysis = AnalysisModel(id=91, video_id=72, status="COMPLETED")
    test = TestModel(
        id=33,
        athlete_id=12,
        distance=10,
        test_type="Velocidad",
        technique="Salida de tacos",
        created_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
    )
    athlete = AthleteModel(
        id=12,
        first_name="Ana",
        last_name="Atleta",
        identification="TEST-12",
        age=18,
        gender="F",
        owner_user_id=3,
    )
    metrics = MetricsModel(
        analysis_id=91,
        average_speed=7.1,
        maximum_speed=8.2,
        stride_length=2.1,
        cadence=3.4,
        posture_score=82,
    )
    return analysis, test, athlete, metrics


@pytest.mark.parametrize(
    ("output_format", "signature"),
    [("pdf", b"%PDF"), ("xlsx", b"PK"), ("csv", b"\xef\xbb\xbf")],
)
async def test_report_generation_persists_downloadable_file(
    output_format: str, signature: bytes
) -> None:
    session = ReportSession(rows=[_report_row()])
    user = User(id=3, email="docente@example.com", hashed_password="hash", full_name="Docente")
    payload = workspace.ReportCreateDTO(name="Informe de prueba", output_format=output_format)

    response = await workspace.generate_report(payload, session, user)

    assert response["id"] is None or response["id"] == session.added.id
    assert session.added.file_content.startswith(signature)
    assert session.added.user_id == 3
    assert session.commits == 1
