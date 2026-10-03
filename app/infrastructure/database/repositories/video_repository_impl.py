from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.video import Video, VideoStatus
from app.domain.repositories.video_repository import VideoRepository
from app.infrastructure.database.models.video_model import VideoModel


class SqlAlchemyVideoRepository(VideoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, video: Video) -> Video:
        model = VideoModel(
            test_id=video.test_id,
            original_filename=video.original_filename,
            storage_path=video.storage_path,
            file_size=video.file_size,
            duration=video.duration,
            fps=video.fps,
            width=video.width,
            height=video.height,
            total_frames=video.total_frames,
            status=video.status.value,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, video_id: int) -> Video | None:
        model = await self._session.get(VideoModel, video_id)
        return self._to_entity(model) if model else None

    async def get_by_test_id(self, test_id: int) -> Video | None:
        result = await self._session.execute(
            select(VideoModel).where(VideoModel.test_id == test_id).order_by(VideoModel.id.desc()).limit(1)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    @staticmethod
    def _to_entity(model: VideoModel) -> Video:
        return Video(
            id=model.id,
            test_id=model.test_id,
            original_filename=model.original_filename,
            storage_path=model.storage_path,
            file_size=model.file_size,
            duration=model.duration,
            fps=model.fps,
            width=model.width,
            height=model.height,
            total_frames=model.total_frames,
            status=VideoStatus(model.status),
            created_at=model.created_at,
        )
