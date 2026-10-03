from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class VideoStatus(str, Enum):
    UPLOADED = "UPLOADED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


@dataclass
class Video:
    test_id: int
    original_filename: str
    storage_path: str
    file_size: int
    id: int | None = None
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    total_frames: int | None = None
    status: VideoStatus = VideoStatus.UPLOADED
    created_at: datetime | None = None
