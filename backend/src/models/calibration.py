from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class CalibrationMetric(Base):
    __tablename__ = "calibration_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evaluator_id: Mapped[str] = mapped_column(nullable=False, index=True)
    correlation: Mapped[Optional[float]] = mapped_column(nullable=True)
    rmse: Mapped[Optional[float]] = mapped_column(nullable=True)
    sample_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
