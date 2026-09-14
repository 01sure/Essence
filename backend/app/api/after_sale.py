"""售后工单：连接访客诉求与人工客服处理结果。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import ROLE_CAN_AGENT
from app.db.session import get_db
from app.models import AdminUser, AfterSaleTicket, ChatSession
from app.services import analytics

router = APIRouter(tags=["after-sale"])


class TicketCreateIn(BaseModel):
    category: str = Field(min_length=2, max_length=30)
    description: str = Field(min_length=5, max_length=2000)
    order_no: str = Field(default="", max_length=32)
    priority: str = Field(default="normal", pattern="^(normal|urgent)$")


class TicketUpdateIn(BaseModel):
    status: str = Field(pattern="^(open|processing|resolved|closed)$")
    resolution: str = Field(default="", max_length=2000)
    assigned_admin_id: int | None = None


def _ticket_json(ticket: AfterSaleTicket, admin_name: str = "") -> dict:
    return {
        "id": ticket.id,
        "session_id": ticket.session_id,
        "order_no": ticket.order_no,
        "category": ticket.category,
        "priority": ticket.priority,
        "status": ticket.status,
        "description": ticket.description,
        "resolution": ticket.resolution,
        "assigned_admin_id": ticket.assigned_admin_id,
        "assigned_admin_name": admin_name,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


@router.post("/api/chat/sessions/{session_id}/after-sale", status_code=201)
async def create_ticket(
    session_id: str,
    body: TicketCreateIn,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    ticket = AfterSaleTicket(
        session_id=session_id,
        order_no=body.order_no.strip(),
        category=body.category.strip(),
        priority=body.priority,
        description=body.description.strip(),
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    await analytics.record_event(
        db, "after_sale_created", session_id,
        {"ticket_id": ticket.id, "category": ticket.category, "priority": ticket.priority},
    )
    return _ticket_json(ticket)


@router.get("/api/chat/sessions/{session_id}/after-sale")
async def session_tickets(session_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(ChatSession, session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = await db.execute(
        select(AfterSaleTicket)
        .where(AfterSaleTicket.session_id == session_id)
        .order_by(AfterSaleTicket.created_at.desc())
    )
    return {"items": [_ticket_json(ticket) for ticket in rows.scalars()]}


@router.get("/api/admin/after-sale-tickets")
async def list_tickets(
    status: str = Query(default=""),
    category: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    stmt = select(AfterSaleTicket).order_by(AfterSaleTicket.updated_at.desc())
    if status:
        stmt = stmt.where(AfterSaleTicket.status == status)
    if category:
        stmt = stmt.where(AfterSaleTicket.category == category)
    rows = await db.execute(stmt)
    tickets = list(rows.scalars())
    admin_ids = {ticket.assigned_admin_id for ticket in tickets if ticket.assigned_admin_id}
    admins = {}
    if admin_ids:
        admin_rows = await db.execute(select(AdminUser).where(AdminUser.id.in_(admin_ids)))
        admins = {admin.id: admin.display_name or admin.username for admin in admin_rows.scalars()}
    return {"items": [_ticket_json(ticket, admins.get(ticket.assigned_admin_id, "")) for ticket in tickets]}


@router.patch("/api/admin/after-sale-tickets/{ticket_id}")
async def update_ticket(
    ticket_id: int,
    body: TicketUpdateIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    ticket = await db.get(AfterSaleTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="售后工单不存在")
    if body.assigned_admin_id is not None:
        target = await db.get(AdminUser, body.assigned_admin_id)
        if not target or not target.active:
            raise HTTPException(status_code=400, detail="指定坐席不存在或已停用")
        ticket.assigned_admin_id = target.id
    elif ticket.assigned_admin_id is None:
        ticket.assigned_admin_id = admin.id
    previous_status = ticket.status
    ticket.status = body.status
    ticket.resolution = body.resolution.strip()
    await db.commit()
    await db.refresh(ticket)
    if previous_status != ticket.status:
        await analytics.record_event(
            db, "after_sale_status_changed", ticket.session_id,
            {"ticket_id": ticket.id, "from": previous_status, "to": ticket.status},
        )
    return _ticket_json(ticket, admin.display_name or admin.username)