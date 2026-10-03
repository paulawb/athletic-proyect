from app.core.exceptions import VideoNotFoundError
from app.domain.entities.analysis import Analysis
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.video_repository import VideoRepository


class CreateAnalysis:
    """Caso de uso de la Fase 8: solo valida que el video exista y crea el
    registro de Analysis en PENDING (seccion 12). No procesa nada -eso lo
    hace ProcessVideoFrames, encolado por separado- para que el endpoint
    pueda responder de inmediato sin esperar el procesamiento."""

    def __init__(self, video_repository: VideoRepository, analysis_repository: AnalysisRepository) -> None:
        self._video_repository = video_repository
        self._analysis_repository = analysis_repository

    async def execute(self, video_id: int) -> Analysis:
        video = await self._video_repository.get_by_id(video_id)
        if video is None:
            raise VideoNotFoundError(f"No existe un video con id={video_id}")

        return await self._analysis_repository.create(
            Analysis(video_id=video_id, total_frames=video.total_frames or 0)
        )
