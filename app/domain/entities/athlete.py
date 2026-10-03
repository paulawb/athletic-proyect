from dataclasses import dataclass
from datetime import datetime


@dataclass
class Athlete:
    first_name: str
    last_name: str
    identification: str
    age: int
    gender: str
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    email: str | None = None
    category: str | None = None
    group_name: str | None = None
    is_active: bool = True
