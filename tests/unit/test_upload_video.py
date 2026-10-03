from __future__ import annotations

import pytest

from app.application.use_cases.get_test_video import GetTestVideo
from app.application.use_cases.get_video import GetVideo
from app.application.use_cases.upload_video import UploadVideo
from app.core.exceptions import (
    InvalidVideoFormatError,
    TestNotFoundError,
    VideoNotFoundError,
    VideoProcessingError,
    VideoTooLargeError,
)
from app.domain.entities.test import Test
from app.domain.entities.video import Video
from app.domain.repositories.test_repository import TestRepository
from app.domain.repositories.video_repository import VideoRepository
from app.domain.services.frame_processor import FrameProcessor, VideoMetadata
from app.domain.services.video_storage import StoredVideo, VideoStorage


class FakeUploadedFile:
    """Doble de fastapi.UploadFile: cumple UploadedFileLike sin depender de FastAPI."""

    def __init__(self, filename: str, content: bytes, content_type: str | None = "video/mp4") -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._served = False

    async def read(self, size: int = -1) -> bytes:
        if self._served:
            return b""
        self._served = True
        return self._content


class FakeTestRepository(TestRepository):
    def __init__(self, tests: list[Test] | None = None) -> None:
        self._tests = {t.id: t for t in (tests or [])}

    async def create(self, test: Test) -> Test:
        self._tests[test.id] = test
        return test

    async def get_by_id(self, test_id: int) -> Test | None:
        return self._tests.get(test_id)

    async def list(self, skip: int = 0, limit: int = 50) -> list[Test]:
        return list(self._tests.values())[skip : skip + limit]

    async def list_by_athlete(self, athlete_id: int) -> list[Test]:
        return [t for t in self._tests.values() if t.athlete_id == athlete_id]

    async def update_status(self, test_id: int, status: str) -> Test:
        test = self._tests[test_id]
        test.status = status
        return test


class FakeVideoRepository(VideoRepository):
    def __init__(self) -> None:
        self._videos: dict[int, Video] = {}
        self._next_id = 1

    async def create(self, video: Video) -> Video:
        video.id = self._next_id
        self._videos[video.id] = video
        self._next_id += 1
        return video

    async def get_by_id(self, video_id: int) -> Video | None:
        return self._videos.get(video_id)

    async def get_by_test_id(self, test_id: int) -> Video | None:
        matches = [v for v in self._videos.values() if v.test_id == test_id]
        return matches[-1] if matches else None


class FakeVideoStorage(VideoStorage):
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, file, destination_id, max_size_bytes=None) -> StoredVideo:
        content = b""
        while chunk := await file.read(1024 * 1024):
            content += chunk
            if max_size_bytes is not None and len(content) > max_size_bytes:
                raise VideoTooLargeError("El video supera el tamano maximo permitido")
        path = f"videos/{destination_id}.mp4"
        self.saved[path] = content
        return StoredVideo(storage_path=path, file_size=len(content))

    def get_absolute_path(self, storage_path: str) -> str:
        return storage_path

    async def delete(self, storage_path: str) -> None:
        self.deleted.append(storage_path)
        self.saved.pop(storage_path, None)


class FakeFrameProcessor(FrameProcessor):
    def __init__(self, metadata: VideoMetadata | None = None, raise_error: bool = False) -> None:
        self._metadata = metadata or VideoMetadata(total_frames=240, fps=60.0, duration=4.0, width=1920, height=1080)
        self._raise_error = raise_error

    def get_video_metadata(self, video_path: str) -> VideoMetadata:
        if self._raise_error:
            raise ValueError("video corrupto simulado")
        return self._metadata

    def iterate_frames(self, video_path: str):
        raise NotImplementedError("no se usa en la Fase 3")


def _existing_test() -> Test:
    return Test(id=1, athlete_id=1, distance=10, test_type="Carrera de velocidad", technique="Salida de tacos")


def _build_use_case(
    test_repository=None, video_storage=None, frame_processor=None, max_size_bytes=500 * 1024 * 1024
) -> UploadVideo:
    return UploadVideo(
        test_repository=test_repository or FakeTestRepository([_existing_test()]),
        video_repository=FakeVideoRepository(),
        video_storage=video_storage or FakeVideoStorage(),
        frame_processor=frame_processor or FakeFrameProcessor(),
        max_size_bytes=max_size_bytes,
    )


async def test_upload_video_succeeds_and_persists_metadata() -> None:
    use_case = _build_use_case()
    file = FakeUploadedFile("carrera_01.mp4", b"contenido-de-prueba")

    video = await use_case.execute(test_id=1, file=file)

    assert video.id == 1
    assert video.test_id == 1
    assert video.total_frames == 240
    assert video.fps == 60.0
    assert video.status.value == "VALIDATED"


async def test_upload_video_raises_when_test_does_not_exist() -> None:
    use_case = _build_use_case(test_repository=FakeTestRepository([]))
    file = FakeUploadedFile("carrera_01.mp4", b"contenido")

    with pytest.raises(TestNotFoundError):
        await use_case.execute(test_id=99, file=file)


async def test_upload_video_rejects_invalid_extension() -> None:
    use_case = _build_use_case()
    file = FakeUploadedFile("carrera_01.avi", b"contenido")

    with pytest.raises(InvalidVideoFormatError):
        await use_case.execute(test_id=1, file=file)


async def test_upload_video_rejects_empty_file() -> None:
    use_case = _build_use_case()
    file = FakeUploadedFile("carrera_01.mp4", b"")

    with pytest.raises(InvalidVideoFormatError):
        await use_case.execute(test_id=1, file=file)


async def test_upload_video_raises_processing_error_when_corrupt() -> None:
    storage = FakeVideoStorage()
    use_case = _build_use_case(video_storage=storage, frame_processor=FakeFrameProcessor(raise_error=True))
    file = FakeUploadedFile("carrera_01.mp4", b"contenido-corrupto")

    with pytest.raises(VideoProcessingError):
        await use_case.execute(test_id=1, file=file)

    # El archivo parcial se elimina: no queda basura en el storage.
    assert storage.saved == {}
    assert len(storage.deleted) == 1


async def test_upload_video_raises_too_large_when_exceeds_limit() -> None:
    use_case = _build_use_case(max_size_bytes=5)
    file = FakeUploadedFile("carrera_01.mp4", b"contenido-mas-largo-que-el-limite")

    with pytest.raises(VideoTooLargeError):
        await use_case.execute(test_id=1, file=file)


async def test_get_video_raises_when_not_found() -> None:
    with pytest.raises(VideoNotFoundError):
        await GetVideo(FakeVideoRepository()).execute(999)


async def test_get_test_video_raises_when_test_has_no_video() -> None:
    with pytest.raises(VideoNotFoundError):
        await GetTestVideo(FakeVideoRepository()).execute(1)
