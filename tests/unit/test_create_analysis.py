import pytest

from app.application.use_cases.create_analysis import CreateAnalysis
from app.core.exceptions import VideoNotFoundError
from app.domain.entities.analysis import AnalysisStatus
from app.domain.entities.video import Video, VideoStatus
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.video_repository import VideoRepository


class FakeVideoRepository(VideoRepository):
    def __init__(self, videos: list[Video] | None = None) -> None:
        self._videos = {v.id: v for v in (videos or [])}

    async def create(self, video: Video) -> Video:
        self._videos[video.id] = video
        return video

    async def get_by_id(self, video_id: int) -> Video | None:
        return self._videos.get(video_id)

    async def get_by_test_id(self, test_id: int) -> Video | None:
        matches = [v for v in self._videos.values() if v.test_id == test_id]
        return matches[-1] if matches else None


class FakeAnalysisRepository(AnalysisRepository):
    def __init__(self) -> None:
        self.created = []
        self._next_id = 1

    async def create(self, analysis):
        analysis.id = self._next_id
        self._next_id += 1
        self.created.append(analysis)
        return analysis

    async def get_by_id(self, analysis_id):
        return next((a for a in self.created if a.id == analysis_id), None)

    async def list(self, skip=0, limit=50):
        return self.created[skip : skip + limit]

    async def list_by_video_id(self, video_id):
        return [a for a in self.created if a.video_id == video_id]

    async def update_progress(self, analysis_id, status, processed_frames, error_message=None):
        raise NotImplementedError("no se usa en estas pruebas")

    async def update_progress_batch(self, analysis_id: int, processed_frames: int) -> None:
        raise NotImplementedError("no se usa en estas pruebas")


def _existing_video(total_frames: int = 45) -> Video:
    return Video(
        id=1,
        test_id=1,
        original_filename="carrera_01.mp4",
        storage_path="videos/test-1.mp4",
        file_size=1024,
        total_frames=total_frames,
        status=VideoStatus.VALIDATED,
    )


async def test_create_analysis_creates_pending_analysis_for_existing_video() -> None:
    use_case = CreateAnalysis(
        video_repository=FakeVideoRepository([_existing_video(total_frames=45)]),
        analysis_repository=FakeAnalysisRepository(),
    )

    analysis = await use_case.execute(video_id=1)

    assert analysis.id is not None
    assert analysis.video_id == 1
    assert analysis.status == AnalysisStatus.PENDING
    assert analysis.total_frames == 45
    assert analysis.processed_frames == 0


async def test_create_analysis_raises_when_video_does_not_exist() -> None:
    use_case = CreateAnalysis(
        video_repository=FakeVideoRepository([]), analysis_repository=FakeAnalysisRepository()
    )

    with pytest.raises(VideoNotFoundError):
        await use_case.execute(video_id=99)
