from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class VideoMetadata:
    total_frames: int
    fps: float
    duration: float
    width: int
    height: int


class FrameProcessor(ABC):
    @abstractmethod
    def iterate_frames(self, video_path: str) -> Iterator[tuple[int, np.ndarray, float]]:
        """Recorre el video cuadro por cuadro sin cargarlo completo en memoria.
        Produce (frame_number, frame, timestamp_segundos) uno a la vez."""
        ...

    @abstractmethod
    def get_video_metadata(self, video_path: str) -> VideoMetadata: ...
