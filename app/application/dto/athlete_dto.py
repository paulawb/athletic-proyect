from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AthleteCreateDTO(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    identification: str = Field(min_length=1, max_length=50)
    age: int = Field(gt=0, le=120)
    gender: str = Field(min_length=1, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=50)
    group_name: str | None = Field(default=None, max_length=80)


class AthleteUpdateDTO(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    identification: str | None = Field(default=None, min_length=1, max_length=50)
    age: int | None = Field(default=None, gt=0, le=120)
    gender: str | None = Field(default=None, min_length=1, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=50)
    group_name: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class AthleteResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    identification: str
    age: int
    gender: str
    email: str | None = None
    category: str | None = None
    group_name: str | None = None
    is_active: bool = True
    test_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
