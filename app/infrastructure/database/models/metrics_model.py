from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetricsModel(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )
    average_speed: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_speed: Mapped[float] = mapped_column(Float, nullable=False)
    stride_length: Mapped[float] = mapped_column(Float, nullable=False)
    cadence: Mapped[float] = mapped_column(Float, nullable=False)
    posture_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
