"""会话管理：人工接入、CAS 抢单、释放/转交、回复、关闭、质检、SSE 实时推流"""
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import ROLE_CAN_AGENT, ROLE_CAN_QA
from app.db.session import get_db
from app.models import AdminUser, ChatMessage, ChatSession
from app.services import session_service
from app.services import sse_bus
from app.state import state

router = APIRouter(prefix="/admin/sessions", tags=["admin-sessions"])


class AdminReplyIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class TransferIn(BaseModel):
    target_admin_id: int


class ScoreIn(BaseModel):
    score: int = Field(ge=0, le=100)
    remark: str = ""


async def _sessions_joined(db: AsyncSession, stmt, page: int, size: int) -> tuple[int, list[dict]]:
    """会话列表（带 admin 坐席名 & 最后一条消息预览）"""
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    stmt = stmt.order_by(ChatSession.updated_at.desc()).offset((page - 1) * size).limit(size)
    # LEFT JOIN 坐席显示名
    rows = (
        await db.execute(
            stmt.join(AdminUser, AdminUser.id == ChatSession.human_admin_id, isouter=True)
            .add_columns(AdminUser.display_name.label("_human_name"))
        )
    ).all()
    sessions: list[ChatSession] = [r[0] for r in rows]
    human_names = {r[0].id: r[1] or "" for r in rows}
    # 取会话最后一条消息作为预览
    previews: dict[str, str] = {}
    if sessions:
        ids = [s.id for s in sessions]
        msgs = (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id.in_(ids))
                .order_by(ChatMessage.session_id, ChatMessage.seq.desc())
            )
        ).scalars().all()
        seen: set[str] = set()
        for m in msgs:
            if m.session_id not in seen:
                seen.add(m.session_id)
                previews[m.session_id] = m.content[:120]
    return total, [
        {
            "id": s.id,
            "visitor_id": s.visitor_id,
            "status": s.status,
            "escalated": bool(s.escalated),
            "rating": s.rating,
            "quality_score": s.quality_score,
            "page_url": s.page_url,
            "human_admin_id": s.human_admin_id,
            "human_admin_name": human_names.get(s.id, ""),
            "assigned_at": s.assigned_at.isoformat() if s.assigned_at else None,
            "last_message": previews.get(s.id, ""),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


@router.get("")
async def list_sessions(
    status: str = "", keyword: str = "", pool: str = "", mine: bool = False,
    page: int = 1, size: int = 20,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    stmt = select(ChatSession)
    if status:
        stmt = stmt.where(ChatSession.status == status)
    if keyword:
        stmt = stmt.where(ChatSession.visitor_id.contains(keyword))
    # pool=waiting：waiting_human 待分配池（不含已被接单的）
    if pool == "waiting":
        stmt = stmt.where(
            ChatSession.status == "waiting_human", ChatSession.human_admin_id.is_(None)
        )
    elif pool == "mine":
        stmt = stmt.where(ChatSession.human_admin_id == admin.id)
    if mine:
        stmt = stmt.where(ChatSession.human_admin_id == admin.id)
    total, items = await _sessions_joined(db, stmt, page, size)
    return {"total": total, "items": items}


@router.get("/stats")
async def pool_stats(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    waiting = (
        await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.status == "waiting_human", ChatSession.human_admin_id.is_(None)
            )
        )
    ).scalar() or 0
    mine_active = (
        await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.status == "human_active", ChatSession.human_admin_id == admin.id
            )
        )
    ).scalar() or 0
    return {"waiting": waiting, "mine_active": mine_active, "capacity": admin.capacity}


# ---------------- SSE 实时推流给坐席端 ----------------

@router.get("/stream")
async def admin_sse_stream(
    request: Request,
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
) -> StreamingResponse:
    """
    坐席端 SSE：
      - event: new_waiting   => 有新会话进入等待池，刷新等待池列表
      - event: pool_refresh  => 状态变化（领取/释放/转交/关闭）
      - event: new_message   => 我接待的某会话有新消息（访客回复/系统消息）
      - event: keepalive     => 心跳（每 25s，防止 nginx 断开）
    """
    q = await sse_bus.subscribe(admin.id)

    async def gen() -> AsyncGenerator[str, None]:
        # 先发一个 connected 让前端知道已连
        yield f"data: {json.dumps({'event': 'connected', 'admin_id': admin.id}, ensure_ascii=False)}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'event': 'keepalive'}, ensure_ascii=False)}\n\n"
        finally:
            await sse_bus.unsubscribe(admin.id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{session_id}")
async def session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    human_name = ""
    if session.human_admin_id:
        owner = await db.get(AdminUser, session.human_admin_id)
        human_name = owner.display_name if owner else ""
    qa_name = ""
    if session.quality_admin_id:
        qa = await db.get(AdminUser, session.quality_admin_id)
        qa_name = qa.display_name if qa else ""
    messages = await session_service.get_messages(db, session_id, limit=500)
    return {
        "session": {
            "id": session.id,
            "visitor_id": session.visitor_id,
            "status": session.status,
            "escalated": bool(session.escalated),
            "rating": session.rating,
            "quality_score": session.quality_score,
            "quality_remark": session.quality_remark,
            "quality_admin_name": qa_name,
            "quality_created_at": session.quality_created_at.isoformat() if session.quality_created_at else None,
            "page_url": session.page_url,
            "human_admin_id": session.human_admin_id,
            "human_admin_name": human_name,
            "assigned_at": session.assigned_at.isoformat() if session.assigned_at else None,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        },
        "messages": [
            {
                "id": m.id, "seq": m.seq, "role": m.role, "content": m.content,
                "intent": m.intent, "meta": m.meta,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


# ---------------- CAS 原子操作：抢单 / 释放 / 转交 ----------------

@router.post("/{session_id}/claim")
async def claim_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    """原子领取：仅 waiting_human 且无人接管时，将 human_admin_id 置为当前坐席。
    受影响行数为 0 时，说明会话被别人先抢到，返回 409。"""
    # 容量检查
    mine = (
        await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.status == "human_active", ChatSession.human_admin_id == admin.id
            )
        )
    ).scalar() or 0
    if mine >= admin.capacity:
        raise HTTPException(status_code=400, detail=f"接待数量已达上限 {admin.capacity}，请先完成现有会话")
    now = datetime.now()
    # CAS：status=waiting_human AND human_admin_id IS NULL 时才允许写入
    result = await db.execute(
        text(
            "UPDATE chat_sessions SET status=:s, human_admin_id=:aid, assigned_at=:ts WHERE id=:sid "
            "AND status='waiting_human' AND human_admin_id IS NULL"
        ),
        {"s": "human_active", "aid": admin.id, "ts": now, "sid": session_id},
    )
    await db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=409, detail="会话已被其他客服接走，请刷新列表")
    await sse_bus.on_pool_changed()
    return {"ok": True, "human_admin_id": admin.id}


@router.post("/{session_id}/release")
async def release_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    """交还到等待池（仅当前接待人可释放）"""
    result = await db.execute(
        text(
            "UPDATE chat_sessions SET status='waiting_human', human_admin_id=NULL, assigned_at=NULL "
            "WHERE id=:sid AND human_admin_id=:aid"
        ),
        {"sid": session_id, "aid": admin.id},
    )
    await db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=409, detail="您不是当前接待人或会话状态已变更")
    await sse_bus.on_pool_changed()
    return {"ok": True}


@router.post("/{session_id}/transfer")
async def transfer_session(
    session_id: str, body: TransferIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    """转交给其他在线客服（仅当前接待人可转）"""
    target = await db.get(AdminUser, body.target_admin_id)
    if not target or target.presence == "offline" or not target.active:
        raise HTTPException(status_code=400, detail="目标坐席不在线或不存在")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="不能转给自己")
    now = datetime.now()
    result = await db.execute(
        text(
            "UPDATE chat_sessions SET human_admin_id=:tid, assigned_at=:ts "
            "WHERE id=:sid AND human_admin_id=:aid"
        ),
        {"tid": target.id, "ts": now, "sid": session_id, "aid": admin.id},
    )
    await db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=409, detail="您不是当前接待人或会话状态已变更")
    # 插入一条系统消息，访客能看到"转接给了 XX"
    await session_service.add_message(
        db, session_id, "system", f"会话已由 {admin.display_name or admin.username} 转交给 {target.display_name or target.username}"
    )
    await sse_bus.on_pool_changed()
    await sse_bus.on_session_message(session_id, target.id, {"role": "system"})
    return {"ok": True, "target_admin_id": target.id}


# ---------------- 人工回复 / 关闭 / 交还 AI ----------------

@router.post("/{session_id}/messages")
async def admin_reply(
    session_id: str, body: AdminReplyIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    """人工客服回复：必须是当前接待人，且会话必须 human_active / waiting_human。
    对 waiting_human 的回复隐式领取。"""
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status not in ("human_active", "waiting_human"):
        raise HTTPException(status_code=400, detail="当前会话状态不可人工回复")
    now = datetime.now()
    # 没有接待人 → 隐式 CAS 领取
    if session.human_admin_id is None:
        result = await db.execute(
            text(
                "UPDATE chat_sessions SET status='human_active', human_admin_id=:aid, assigned_at=:ts "
                "WHERE id=:sid AND human_admin_id IS NULL"
            ),
            {"aid": admin.id, "ts": now, "sid": session_id},
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise HTTPException(status_code=409, detail="会话已被其他客服接走")
        session.human_admin_id = admin.id
    elif session.human_admin_id != admin.id:
        raise HTTPException(status_code=403, detail="该会话由其他客服接待")
    msg = await session_service.add_message(
        db, session_id, "admin", body.content,
        meta={"admin_id": admin.id, "admin_name": admin.display_name or admin.username},
    )
    # 访客端通过轮询取；坐席端如果是"我"发送的，不用再推给自己
    return {"message_id": msg.id, "seq": msg.seq}


@router.post("/{session_id}/close")
async def close_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.status = "closed"
    await db.commit()
    await sse_bus.on_pool_changed()
    return {"ok": True}


@router.post("/{session_id}/back-to-ai")
async def back_to_ai(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    """人工处理完毕，交还 AI（清空 human_admin_id）"""
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.human_admin_id and session.human_admin_id != admin.id:
        raise HTTPException(status_code=403, detail="该会话由其他客服接待")
    session.status = "active"
    session.human_admin_id = None
    session.assigned_at = None
    await db.commit()
    await session_service.add_message(
        db, session_id, "system", "会话已交还 AI 客服继续服务"
    )
    await sse_bus.on_pool_changed()
    return {"ok": True}


@router.get("/waiting/count")
async def waiting_count(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    count = (
        await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.status == "waiting_human", ChatSession.human_admin_id.is_(None)
            )
        )
    ).scalar() or 0
    return {"count": count}


# ---------------- 质检（客服主管） ----------------

@router.post("/{session_id}/quality")
async def quality_score(
    session_id: str, body: ScoreIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_QA)),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.quality_score = body.score
    session.quality_remark = (body.remark or "")[:500]
    session.quality_admin_id = admin.id
    session.quality_created_at = datetime.now()
    await db.commit()
    return {"ok": True}
