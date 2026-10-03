from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TestStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class Test:
    athlete_id: int
    distance: int
    test_type: str
    technique: str
    id: int | None = None
    status: TestStatus = TestStatus.PENDING
    created_at: datetime | None = None
