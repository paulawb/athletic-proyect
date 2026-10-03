from abc import ABC, abstractmethod

from app.domain.entities.video import Video


class VideoRepository(ABC):
    @abstractmethod
    async def create(self, video: Video) -> Video: ...

    @abstractmethod
    async def get_by_id(self, video_id: int) -> Video | None: ...

    @abstractmethod
    async def get_by_test_id(self, test_id: int) -> Video | None: ...
