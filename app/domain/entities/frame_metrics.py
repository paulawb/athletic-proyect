from dataclasses import dataclass
from typing import Any


@dataclass
class FrameMetrics:
    analysis_id: int
    frame_number: int
    timestamp: float
    x_position: float
    y_position: float
    speed: float
    stride_phase: str
    posture_score: float
    id: int | None = None
    keypoints: list[dict[str, Any]] | None = None
