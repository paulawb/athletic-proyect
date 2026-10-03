from app.core.exceptions import VideoNotFoundError
from app.domain.entities.video import Video
from app.domain.repositories.video_repository import VideoRepository


class GetTestVideo:
    def __init__(self, video_repository: VideoRepository) -> None:
        self._video_repository = video_repository

    async def execute(self, test_id: int) -> Video:
        video = await self._video_repository.get_by_test_id(test_id)
        if video is None:
            raise VideoNotFoundError(f"La prueba con id={test_id} no tiene un video cargado")
        return video
