from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class AnalyticsEvent(Base):
    """行为/业务事件：intent / escalation / product_click / rating / recommendation_shown ..."""

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
