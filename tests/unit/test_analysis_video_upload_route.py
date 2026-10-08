from fastapi import BackgroundTasks

from app.domain.entities.analysis import Analysis, AnalysisStatus
from app.domain.entities.user import User
from app.domain.entities.video import Video
from app.presentation.api.v1.routes import analisis


class FakeUploadVideo:
    def __init__(self, **kwargs) -> None:
        pass

    async def execute(self, test_id, video):
        return Video(
            id=42,
            test_id=test_id,
            original_filename="sprint.mp4",
            storage_path="videos/sprint.mp4",
            file_size=1024,
        )


class FakeCreateAnalysis:
    video_id = None

    def __init__(self, **kwargs) -> None:
        pass

    async def execute(self, video_id):
        type(self).video_id = video_id
        return Analysis(id=7, video_id=video_id, status=AnalysisStatus.PENDING)


async def test_upload_route_creates_analysis_using_persisted_video_id(monkeypatch) -> None:
    async def require_owned_test(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(analisis, "UploadVideo", FakeUploadVideo)
    monkeypatch.setattr(analisis, "CreateAnalysis", FakeCreateAnalysis)
    monkeypatch.setattr(analisis, "require_owned_test", require_owned_test)

    response = await analisis.upload_and_queue_analysis(
        test_id=3,
        video=object(),
        background_tasks=BackgroundTasks(),
        session=object(),
        current_user=User(id=1, email="docente@example.com", hashed_password="hash", full_name="Docente"),
    )

    assert response.video_id == 42
    assert response.analysis_id == 7
    assert response.status == AnalysisStatus.PENDING
    assert FakeCreateAnalysis.video_id == 42
