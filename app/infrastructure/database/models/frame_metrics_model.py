from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FrameMetricsModel(Base):
    __tablename__ = "frame_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    x_position: Mapped[float] = mapped_column(Float, nullable=False)
    y_position: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False)
    stride_phase: Mapped[str] = mapped_column(String(20), nullable=False)
    posture_score: Mapped[float] = mapped_column(Float, nullable=False)
    keypoints: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
