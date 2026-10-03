"""DTOs para el endpoint combinado de Fase 12: subir video + encolar
procesamiento en una sola llamada (POST /api/v1/analisis/procesar-video)."""
from pydantic import BaseModel


class ProcessVideoResponseDTO(BaseModel):
    """Respuesta 202: el video se subió, el Analysis se creó en PENDING y
    el pipeline de procesamiento está encolado. El frontend debe sondear
    GET /api/v1/analisis/{analysis_id} para seguir el progreso."""

    video_id: int
    analysis_id: int
    status: str
    message: str = "Video subido y analisis en cola para procesamiento"