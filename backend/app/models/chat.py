from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatSession(Base):
    """访客会话。status: active(AI)/waiting_human/human_active/closed"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    visitor_id: Mapped[str] = mapped_column(String(64), index=True)
    page_url: Mapped[str] = mapped_column(String(500), default="")
    # 兼容老库 user_ip：历史字段 user_ip（有 NOT NULL 约束）；新代码使用 ip（新列）
    user_ip: Mapped[str] = mapped_column(String(64), default="")
    ua: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    escalated: Mapped[int] = mapped_column(Integer, default=0)
    # 兼容老库 intent_last NOT NULL；新版用消息里 intent 字段，这里仅保留默认值
    intent_last: Mapped[str] = mapped_column(String(30), default="")
    # 当接待的坐席 ID（CAS 原子写入，避免抢单冲突）
    human_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 质检分（主管打分 0-100），质检人 ID，质检备注
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_remark: Mapped[str] = mapped_column(String(500), default="")
    quality_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    """会话消息。role: user / assistant / admin / system"""

    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_chat_messages_session_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)  # user / assistant / admin / system
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # admin 回复附带的坐席名/ID 等
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
