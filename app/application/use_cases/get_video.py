from app.core.exceptions import VideoNotFoundError
from app.domain.entities.video import Video
from app.domain.repositories.video_repository import VideoRepository


class GetVideo:
    def __init__(self, video_repository: VideoRepository) -> None:
        self._video_repository = video_repository

    async def execute(self, video_id: int) -> Video:
        video = await self._video_repository.get_by_id(video_id)
        if video is None:
            raise VideoNotFoundError(f"No existe un video con id={video_id}")
        return video
