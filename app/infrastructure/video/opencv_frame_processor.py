from typing import Iterator

import cv2
import numpy as np

from app.domain.services.frame_processor import FrameProcessor, VideoMetadata


class OpenCVFrameProcessor(FrameProcessor):
    """Primera implementacion real de FrameProcessor (seccion 8), con OpenCV.

    get_video_metadata() es lo que usa la Fase 3 para validar el video recien
    subido (duracion, fps, resolucion, total de cuadros) sin leerlo cuadro
    por cuadro. iterate_frames() ya queda lista para el pipeline de analisis
    de la Fase 4, que sí recorre el video completo, un cuadro a la vez y sin
    cargarlo entero en memoria.
    """

    def get_video_metadata(self, video_path: str) -> VideoMetadata:
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"No se pudo abrir el video: {video_path}")
        try:
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = (total_frames / fps) if fps > 0 else 0.0
            return VideoMetadata(
                total_frames=total_frames, fps=fps, duration=duration, width=width, height=height
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
        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                timestamp = (frame_number / fps) if fps > 0 else 0.0
                yield frame_number, frame, timestamp
                frame_number += 1
        finally:
            capture.release()
