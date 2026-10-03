from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AnalysisStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Analysis:
    video_id: int
    id: int | None = None
    status: AnalysisStatus = AnalysisStatus.PENDING
    processed_frames: int = 0
    total_frames: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None

    @property
    def progress_percentage(self) -> int:
        if self.total_frames == 0:
            return 0
        return round((self.processed_frames / self.total_frames) * 100)
