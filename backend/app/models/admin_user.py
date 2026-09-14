from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminUser(Base):
    """后台管理/客服坐席账号"""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(50), default="")
    # super_admin / admin / team_leader / agent / analyst
    role: Mapped[str] = mapped_column(String(20), default="agent", index=True)
    # 坐席在线状态：online / offline / busy
    presence: Mapped[str] = mapped_column(String(16), default="offline")
    # 同时接待的会话上限（仅 agent 生效）
    capacity: Mapped[int] = mapped_column(Integer, default=8)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 上一次 presence 变更时间（用于计算在线时长）
    presence_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
