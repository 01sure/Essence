"""售后工单：把聊天中的售后诉求沉淀为可跟进、可统计的业务对象。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AfterSaleTicket(Base):
    __tablename__ = "after_sale_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)
    order_no: Mapped[str] = mapped_column(String(32), default="", index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    priority: Mapped[str] = mapped_column(String(12), default="normal")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    description: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text, default="")
    assigned_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )