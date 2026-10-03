from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities.analysis import AnalysisStatus


class AnalysisCreateDTO(BaseModel):
    video_id: int = Field(gt=0)


class AnalysisCreatedResponseDTO(BaseModel):
    """Respuesta inmediata de POST /api/v1/analisis (seccion 13): el
    analisis se crea y se encola, pero la respuesta no espera a que termine
    de procesarse (Fase 8). Para consultar avance o resultado, sondear
    GET /api/v1/analisis/{analysis_id} y, cuando este COMPLETED,
    GET /api/v1/analisis/{analysis_id}/metricas."""

    analysis_id: int
    status: AnalysisStatus
    message: str


class AnalysisResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    status: AnalysisStatus
    processed_frames: int
    total_frames: int
    progress_percentage: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None


class AnalysisMetricsResponseDTO(BaseModel):
    """Respuesta de GET /api/v1/analisis/{id}/metricas (seccion 14-15):
    las metricas ya persistidas, no una vista previa en memoria."""

    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    average_speed: float
    maximum_speed: float
    stride_length: float
    cadence: float
    posture_score: float
    created_at: datetime | None = None
