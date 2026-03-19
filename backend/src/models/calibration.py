from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class CalibrationMetric(Base):
    __tablename__ = "calibration_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evaluator_id: Mapped[str] = mapped_column(nullable=False, index=True)
    score_type: Mapped[Optional[str]] = mapped_column(nullable=True, index=True)  # e.g. "helpfulness"
    correlation: Mapped[Optional[float]] = mapped_column(nullable=True)  # alias for pearson
    pearson_correlation: Mapped[Optional[float]] = mapped_column(nullable=True)
    spearman_correlation: Mapped[Optional[float]] = mapped_column(nullable=True)
    rmse: Mapped[Optional[float]] = mapped_column(nullable=True)
    precision: Mapped[Optional[float]] = mapped_column(nullable=True)
    recall: Mapped[Optional[float]] = mapped_column(nullable=True)
    f1: Mapped[Optional[float]] = mapped_column(nullable=True)
    sample_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    divergence_detected: Mapped[bool] = mapped_column(default=False, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
