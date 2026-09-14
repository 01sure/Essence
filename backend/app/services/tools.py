"""业务工具：订单/物流查询。

生产对接真实商城时，只需将 query_orders / query_logistics 替换为调用商城内部 API 的实现，
Agent 编排层无需改动。
"""
import logging
import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ORDER_NO_RE = re.compile(r"(?i)\bHU\d{8,20}\b")

STATUS_TEXT = {
    "paid": "已付款，商家配货中",
    "shipped": "已发货，运输途中",
    "delivered": "已送达，待签收确认",
    "completed": "已完成",
    "refunding": "退款/退货处理中",
    "refunded": "已退款",
    "closed": "已关闭",
}


def extract_entities(text: str) -> dict:
    """从文本中提取订单号 / 手机号（规则优先，补充 LLM 结果）"""
    return {
        "order_no": (ORDER_NO_RE.search(text).group() if ORDER_NO_RE.search(text) else ""),
        "phone": (PHONE_RE.search(text).group() if PHONE_RE.search(text) else ""),
    }


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else phone


def format_order(order: Order) -> str:
    items = "、".join(
        f"{it.get('name', '')}x{it.get('qty', 1)}" for it in (order.items or [])
    )
    lines = [
        f"订单号 {order.order_no}：{items}，合计 ¥{order.total}",
        f"状态：{STATUS_TEXT.get(order.status, order.status)}"
        + (f"（{order.status_note}）" if order.status_note else ""),
    ]
    if order.logistics_company:
        lines.append(f"物流：{order.logistics_company} {order.logistics_no}")
    if order.address:
        lines.append(f"收货：{mask_phone(order.phone)} {order.address}")
    return "\n".join(lines)


async def query_orders(db: AsyncSession, order_no: str = "", phone: str = "") -> list[Order]:
    """按订单号或手机号查订单；两者都为空时返回空"""
    stmt = select(Order)
    if order_no:
        stmt = stmt.where(Order.order_no == order_no.upper())
    elif phone:
        stmt = stmt.where(Order.phone == phone)
    else:
        return []
    rows = (await db.execute(stmt.order_by(Order.created_at.desc()).limit(3))).scalars().all()
    return list(rows)


async def search_orders_fuzzy(db: AsyncSession, phone: str) -> list[Order]:
    if not phone:
        return []
    stmt = select(Order).where(or_(Order.phone == phone)).limit(3)
    return list((await db.execute(stmt)).scalars().all())


def orders_context(orders: list[Order]) -> str:
    if not orders:
        return (
            "【订单查询结果】未匹配到订单。请引导用户提供订单号（格式 HU+日期+序号）"
            "或下单手机号后再查询。"
        )
    return "【订单查询结果】\n" + "\n\n".join(format_order(o) for o in orders)
