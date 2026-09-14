"""行为埋点与看板统计"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsEvent, AfterSaleTicket, ChatMessage, ChatSession


async def record_event(
    db: AsyncSession, event_type: str, session_id: str | None = None, payload: dict | None = None
) -> None:
    db.add(AnalyticsEvent(session_id=session_id, event_type=event_type, payload=payload))
    await db.commit()


async def dashboard_stats(db: AsyncSession) -> dict:
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)

    # 今日会话 / 总会话
    today_sessions = (
        await db.execute(
            select(func.count(ChatSession.id)).where(ChatSession.created_at >= today_start)
        )
    ).scalar() or 0
    total_sessions = (await db.execute(select(func.count(ChatSession.id)))).scalar() or 0

    # 今日消息
    today_messages = (
        await db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= today_start)
        )
    ).scalar() or 0

    # 转人工率 / AI 解决率（以全部会话为分母）
    escalated = (
        await db.execute(select(func.count(ChatSession.id)).where(ChatSession.escalated == 1))
    ).scalar() or 0
    escalation_rate = round(escalated / total_sessions, 4) if total_sessions else 0.0
    ai_resolution_rate = round(1 - escalation_rate, 4) if total_sessions else 1.0

    # 满意度均分
    avg_rating = (
        await db.execute(select(func.avg(ChatSession.rating)).where(ChatSession.rating.isnot(None)))
    ).scalar()
    avg_rating = round(float(avg_rating), 2) if avg_rating else None

    # 意图分布（近7天 assistant 消息的 intent 字段）
    intent_rows = (
        await db.execute(
            select(ChatMessage.intent, func.count(ChatMessage.id))
            .where(
                ChatMessage.role == "assistant",
                ChatMessage.intent.isnot(None),
                ChatMessage.created_at >= week_start,
            )
            .group_by(ChatMessage.intent)
        )
    ).all()

    # 近7日会话趋势
    trend_rows = (
        await db.execute(
            select(func.date(ChatSession.created_at), func.count(ChatSession.id))
            .where(ChatSession.created_at >= week_start)
            .group_by(func.date(ChatSession.created_at))
            .order_by(func.date(ChatSession.created_at))
        )
    ).all()

    # 商品点击 Top5
    click_rows = (
        await db.execute(
            select(AnalyticsEvent.payload, func.count(AnalyticsEvent.id))
            .where(
                AnalyticsEvent.event_type == "product_click",
                AnalyticsEvent.created_at >= week_start,
            )
            .group_by(AnalyticsEvent.payload)
            .order_by(func.count(AnalyticsEvent.id).desc())
            .limit(5)
        )
    ).all()

    ticket_rows = (
        await db.execute(
            select(AfterSaleTicket.status, func.count(AfterSaleTicket.id))
            .group_by(AfterSaleTicket.status)
        )
    ).all()
    ticket_category_rows = (
        await db.execute(
            select(AfterSaleTicket.category, func.count(AfterSaleTicket.id))
            .group_by(AfterSaleTicket.category)
            .order_by(func.count(AfterSaleTicket.id).desc())
            .limit(5)
        )
    ).all()

    return {
        "today_sessions": today_sessions,
        "total_sessions": total_sessions,
        "today_messages": today_messages,
        "escalation_rate": escalation_rate,
        "ai_resolution_rate": ai_resolution_rate,
        "avg_rating": avg_rating,
        "intent_distribution": [
            {"intent": r[0] or "unknown", "count": r[1]} for r in intent_rows
        ],
        "session_trend": [
            {"date": str(r[0]), "count": r[1]} for r in trend_rows
        ],
        "top_clicked_products": [
            {"product": (r[0] or {}).get("name", "未知"), "count": r[1]} for r in click_rows
        ],
        "after_sale": {
            "by_status": [{"status": r[0], "count": r[1]} for r in ticket_rows],
            "top_categories": [{"category": r[0], "count": r[1]} for r in ticket_category_rows],
        },
    }
