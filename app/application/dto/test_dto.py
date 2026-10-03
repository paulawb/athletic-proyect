from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities.test import TestStatus


class TestCreateDTO(BaseModel):
    athlete_id: int = Field(gt=0)
    distance: int = Field(gt=0)
    test_type: str = Field(min_length=1, max_length=50)
    technique: str = Field(min_length=1, max_length=50)
    test_date: date | None = None


class TestResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    distance: int
    test_type: str
    technique: str
    status: TestStatus
    created_at: datetime | None = None
    analysis_status: str | None = None
    average_speed: float | None = None
    maximum_speed: float | None = None
    stride_length: float | None = None
    cadence: float | None = None
    posture_score: float | None = None
