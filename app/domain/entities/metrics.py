from dataclasses import dataclass
from datetime import datetime


@dataclass
class Metrics:
    analysis_id: int
    average_speed: float
    maximum_speed: float
    stride_length: float
    cadence: float
    posture_score: float
    id: int | None = None
    created_at: datetime | None = None
