"""访客侧聊天 API（SSE 流式）"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import chat_rate_limit, client_ip
from app.db.session import get_db
from app.models import ChatSession
from app.services import analytics, session_service, sse_bus
from app.services.agent import DEFAULT_GREETING
from app.services.settings_cache import settings_cache
from app.state import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionIn(BaseModel):
    visitor_id: str = Field(max_length=64)
    page_url: str = Field(default="", max_length=500)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class EventIn(BaseModel):
    event_type: str = Field(max_length=40)
    payload: dict | None = None


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


@router.post("/sessions", dependencies=[Depends(chat_rate_limit)])
async def create_session(body: CreateSessionIn, request: Request, db: AsyncSession = Depends(get_db)):
    session = await session_service.create_session(
        db, visitor_id=body.visitor_id, page_url=body.page_url, user_ip=client_ip(request)
    )
    greeting = await settings_cache.get(db, "opening_greeting", DEFAULT_GREETING)
    return {"session_id": session.id, "greeting": greeting}


@router.get("/greeting")
async def greeting(db: AsyncSession = Depends(get_db)):
    return {"greeting": await settings_cache.get(db, "opening_greeting", DEFAULT_GREETING)}


@router.post("/sessions/{session_id}/stream", dependencies=[Depends(chat_rate_limit)])
async def chat_stream(
    session_id: str, body: MessageIn, db: AsyncSession = Depends(get_db)
):
    if state.agent is None:
        raise HTTPException(status_code=503, detail="服务初始化中，请稍后重试")
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status == "closed":
        raise HTTPException(status_code=400, detail="会话已结束，请重新发起咨询")

    # 访客新消息先入库（用于坐席侧看到消息内容）；AI 回复由 agent 继续处理
    user_msg = await session_service.add_message(db, session.id, "user", body.content)
    # 若当前会话正由人接待 → 推送给该坐席（SSE new_message）
    if session.status in ("human_active", "waiting_human"):
        await sse_bus.on_session_message(
            session.id, session.human_admin_id,
            {"role": "user", "seq": user_msg.seq, "content": body.content},
        )
    # waiting_human 会话由访客再次发消息时，也刷新等待池（列表按更新时间排序）
    if session.status == "waiting_human" and session.human_admin_id is None:
        await sse_bus.on_pool_changed()

    # 关键词快捷转人工：不用等 LLM 返回 escalated，直接切 status
    quick_escalate_keywords = ("转人工", "人工客服", "客服", "人工", "人工服务", "找客服", "我要人工")
    if session.status == "active" and any(body.content.strip() == kw or body.content.strip().startswith(kw) for kw in quick_escalate_keywords):
        session.status = "waiting_human"
        session.escalated = 1
        await db.commit()
        await session_service.add_message(
            db, session.id, "system", "系统已为您接入人工客服，请稍候，客服代表将尽快与您联系。",
            intent="escalated",
        )
        # 广播新等待会话入池
        await sse_bus.on_new_waiting(session.id, session.visitor_id)
        # SSE 回给 widget：escalated 事件
        async def quick_escalated_stream():
            yield f"data: {json.dumps({'type':'escalated','message':'正在为您接入人工客服…'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(
            quick_escalated_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    agent = state.agent

    async def event_stream():
        try:
            async for event in agent.respond_stream(db, session, body.content, user_persisted=True):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                # 如果 AI 侧已把会话切换为 escalated（waiting_human 待人工），广播到等待池
                if event.get("type") == "escalated":
                    await sse_bus.on_new_waiting(session.id, session.visitor_id)
        except Exception:
            logger.exception("聊天流异常 session=%s", session_id)
            yield f"data: {json.dumps({'type': 'error', 'message': '服务异常，请稍后重试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 关闭缓冲
        },
    )


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: str, after_seq: int = 0, db: AsyncSession = Depends(get_db)
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await session_service.get_messages(db, session_id, limit=50, after_seq=after_seq)
    return {
        "status": session.status,
        "messages": [
            {
                "id": m.id,
                "seq": m.seq,
                "role": m.role,
                "content": m.content,
                "meta": m.meta,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.post("/sessions/{session_id}/events", status_code=204)
async def track_event(session_id: str, body: EventIn, db: AsyncSession = Depends(get_db)):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    await analytics.record_event(db, body.event_type, session_id, body.payload)


@router.post("/sessions/{session_id}/rating")
async def rate_session(session_id: str, body: RatingIn, db: AsyncSession = Depends(get_db)):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.rating = body.rating
    await db.commit()
    await analytics.record_event(db, "rating", session_id, {"rating": body.rating})
    return {"ok": True}


@router.post("/sessions/{session_id}/reopen")
async def reopen(session_id: str, db: AsyncSession = Depends(get_db)):
    """人工结束后用户重新咨询：回到 AI 接待"""
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.status = "active"
    session.human_admin_id = None
    session.assigned_at = None
    await db.commit()
    await sse_bus.on_pool_changed()
    return {"ok": True}
