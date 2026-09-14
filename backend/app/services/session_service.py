"""会话与消息读写"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession, visitor_id: str, page_url: str = "", user_ip: str = ""
) -> ChatSession:
    ip = (user_ip or "")[:64]
    session = ChatSession(
        id=str(uuid.uuid4()),
        visitor_id=visitor_id,
        page_url=page_url[:500],
        ip=ip,
        user_ip=ip,  # 兼容老库列
    )
    db.add(session)
    await db.commit()
    return session


async def get_session(db: AsyncSession, session_id: str) -> ChatSession | None:
    return await db.get(ChatSession, session_id)


async def next_seq(db: AsyncSession, session_id: str) -> int:
    max_seq = (
        await db.execute(
            select(func.max(ChatMessage.seq)).where(ChatMessage.session_id == session_id)
        )
    ).scalar()
    return (max_seq or 0) + 1


async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    meta: dict | None = None,
) -> ChatMessage:
    """写入消息；并发下 seq 冲突时重试（唯一约束兜底）"""
    for attempt in range(3):
        seq = await next_seq(db, session_id)
        msg = ChatMessage(
            session_id=session_id, seq=seq, role=role, content=content, intent=intent, meta=meta
        )
        db.add(msg)
        try:
            await db.commit()
            return msg
        except IntegrityError:
            await db.rollback()
            logger.warning("seq 冲突重试 session=%s attempt=%s", session_id, attempt + 1)
    raise RuntimeError(f"写入消息失败（seq 冲突重试耗尽）session={session_id}")


async def get_messages(
    db: AsyncSession, session_id: str, limit: int = 50, after_seq: int = 0
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.seq > after_seq)
        .order_by(ChatMessage.seq.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return list(reversed(rows))


async def get_history_for_prompt(db: AsyncSession, session_id: str, turns: int) -> list[dict]:
    """取最近 N 条 user/assistant/admin 消息用于提示词（不含 system）"""
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_(["user", "assistant", "admin"]),
        )
        .order_by(ChatMessage.seq.desc())
        .limit(turns)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M %Z")
