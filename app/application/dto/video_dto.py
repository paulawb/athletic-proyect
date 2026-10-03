from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.entities.video import VideoStatus


class VideoResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_id: int
    original_filename: str
    file_size: int
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    total_frames: int | None = None
    status: VideoStatus
    created_at: datetime | None = None
