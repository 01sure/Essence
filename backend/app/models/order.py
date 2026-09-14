from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class Order(Base):
    """示例订单表。生产环境应通过适配器对接真实商城订单系统（见 services/tools.py）。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    receiver: Mapped[str] = mapped_column(String(50), default="")
    items: Mapped[list] = mapped_column(JSON)  # [{name, qty, price, product_id}]
    total: Mapped[float] = mapped_column(Numeric(10, 2))
    # paid / shipped / delivered / completed / refunding / refunded / closed
    status: Mapped[str] = mapped_column(String(20), default="paid")
    status_note: Mapped[str] = mapped_column(String(200), default="")
    logistics_company: Mapped[str] = mapped_column(String(50), default="")
    logistics_no: Mapped[str] = mapped_column(String(50), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
