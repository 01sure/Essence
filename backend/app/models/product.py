from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str] = mapped_column(String(50), default="Amazfit")
    category: Mapped[str] = mapped_column(String(50), index=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    original_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=4.8)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)  # 卖点标签
    description: Mapped[str] = mapped_column(Text, default="")
    selling_points: Mapped[list | None] = mapped_column(JSON, nullable=True)  # FABE 卖点
    url: Mapped[str] = mapped_column(String(500), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    es_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
