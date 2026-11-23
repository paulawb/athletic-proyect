from pathlib import Path
from typing import Iterator
import os
import subprocess
import tempfile

import cv2
import numpy as np

from app.domain.services.frame_processor import FrameProcessor, VideoMetadata


_HEVC_FOURCCS = {"hev1", "hvc1", "hevc", "hev "}


def _fourcc_name(capture: cv2.VideoCapture) -> str:
    raw = int(capture.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((raw >> (8 * i)) & 0xFF) for i in range(4)).lower()


def _transcode_hevc_to_h264(video_path: str) -> bool:
    """Transcode HEVC/H.265 to browser-compatible H.264 MP4.

    OpenCV can process HEVC in some deployments, but browsers often cannot
    decode it. Keeping a H.264 MP4 copy makes the same stored file usable by
    both the analysis pipeline and the browser.
    """
    source = Path(video_path)
    if not source.is_file():
        return False

    fd, temp_name = tempfile.mkstemp(suffix=".mp4", dir=str(source.parent))
    os.close(fd)
    temp_path = Path(temp_name)

    command = [
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k", str(temp_path),
    ]
    try:
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0 or temp_path.stat().st_size <= 0:
            temp_path.unlink(missing_ok=True)
            return False
        os.replace(temp_path, source)
        return True
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        temp_path.unlink(missing_ok=True)
        return False


class OpenCVFrameProcessor(FrameProcessor):
    """Real FrameProcessor backed by OpenCV."""

    def get_video_metadata(self, video_path: str) -> VideoMetadata:
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"No se pudo abrir el video: {video_path}")
        try:
            codec = _fourcc_name(capture)
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

            position_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
            duration = (total_frames / fps) if fps > 0 else 0.0

            # Some phone recordings expose frame count but do not expose a
            # reliable duration through that property. Reading metadata through
            # the last successfully readable frame is more robust.
            if duration <= 0:
                duration = position_ms / 1000
        finally:
            capture.release()

        if codec in _HEVC_FOURCCS:
            _transcode_hevc_to_h264(video_path)

        # Re-open after transcoding so the database stores the final dimensions,
        # frame count and duration of the browser-compatible file.
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"No se pudo leer el video transcodificado: {video_path}")
        try:
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = (total_frames / fps) if fps > 0 else duration
            return VideoMetadata(
                total_frames=total_frames,
                fps=fps,
                duration=duration,
                width=width,
                height=height,
            )
        finally:
            capture.release()

    def iterate_frames(self, video_path: str) -> Iterator[tuple[int, np.ndarray, float]]:
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"No se pudo abrir el video: {video_path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
        frame_number = 0
        previous_timestamp = -1.0
        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                position_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
                if frame_number == 0:
                    timestamp = max(position_ms, 0.0) / 1000
                elif position_ms > 0:
                    timestamp = position_ms / 1000
                else:
                    timestamp = (frame_number / fps) if fps > 0 else 0.0
                if timestamp <= previous_timestamp:
                    timestamp = previous_timestamp + ((1 / fps) if fps > 0 else 0.001)
                previous_timestamp = timestamp
                yield frame_number, frame, timestamp
                frame_number += 1
        finally:
            capture.release()
