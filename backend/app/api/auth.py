"""管理员认证"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import (
    ROLE_ADMIN,
    ROLE_ANALYST,
    ROLE_AGENT,
    ROLE_CAN_AGENT,
    ROLE_CAN_ANALYZE,
    ROLE_CAN_QA,
    ROLE_CAN_USER_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_TEAM_LEADER,
    ROLE_DESC,
    has_any_role,
    role_display,
)
from app.core.security import create_admin_token, hash_password, verify_password
from app.db.session import get_db
from app.models import AdminUser

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.username == body.username))
    ).scalar_one_or_none()
    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not admin.active:
        raise HTTPException(status_code=401, detail="账号已停用，请联系超级管理员")
    now = datetime.now()
    admin.last_login_at = now
    # agent 角色登录时自动把 presence 置为 online（下班需手动 off）
    if admin.role in (ROLE_AGENT, ROLE_TEAM_LEADER):
        admin.presence = "online"
        admin.presence_updated_at = now
    await db.commit()
    return {
        "token": create_admin_token(admin.id, admin.username),
        "user": {
            "id": admin.id,
            "username": admin.username,
            "display_name": admin.display_name,
            "role": admin.role,
            "role_label": role_display(admin.role),
            "presence": admin.presence,
            "capacity": admin.capacity,
            "can_configure": has_any_role(admin.role, ("super_admin", ROLE_ADMIN)),
            "can_agent": has_any_role(admin.role, ROLE_CAN_AGENT),
            "can_qa": has_any_role(admin.role, ROLE_CAN_QA),
            "can_user_admin": has_any_role(admin.role, ROLE_CAN_USER_ADMIN),
            "can_analyze": has_any_role(admin.role, ROLE_CAN_ANALYZE),
        },
    }


@router.get("/me")
async def me(admin: AdminUser = Depends(require_role())):
    return {
        "id": admin.id,
        "username": admin.username,
        "display_name": admin.display_name,
        "role": admin.role,
        "role_label": role_display(admin.role),
        "presence": admin.presence,
        "capacity": admin.capacity,
        "can_configure": has_any_role(admin.role, ("super_admin", ROLE_ADMIN)),
        "can_agent": has_any_role(admin.role, ROLE_CAN_AGENT),
        "can_qa": has_any_role(admin.role, ROLE_CAN_QA),
        "can_user_admin": has_any_role(admin.role, ROLE_CAN_USER_ADMIN),
        "can_analyze": has_any_role(admin.role, ROLE_CAN_ANALYZE),
    }


# ---------------- 坐席状态 ----------------

class PresenceIn(BaseModel):
    presence: str = Field(pattern=r"^(online|offline|busy)$")


@router.put("/presence")
async def set_presence(
    body: PresenceIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    admin.presence = body.presence
    admin.presence_updated_at = datetime.now()
    await db.commit()
    return {"ok": True, "presence": admin.presence}


# ---------------- 账号管理（只有 super_admin） ----------------

class UserCreateIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = ROLE_AGENT
    capacity: int = 8
    active: bool = True


class UserUpdateIn(BaseModel):
    display_name: str | None = None
    role: str | None = None
    capacity: int | None = None
    active: bool | None = None
    password: str | None = None  # 不传则不改


@router.get("/roles")
async def list_roles(_: AdminUser = Depends(require_role())):
    return [
        {
            "key": r.key,
            "display": r.display,
            "can_view": r.can_view,
            "can_configure": r.can_configure,
            "can_agent": r.can_agent,
            "can_qa": r.can_qa,
            "can_user_admin": r.can_user_admin,
        }
        for r in ROLE_DESC
    ]


@router.get("/users")
async def list_users(
    keyword: str = "", page: int = 1, size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_USER_ADMIN)),
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    stmt = select(AdminUser)
    if keyword:
        stmt = stmt.where(
            (AdminUser.username.contains(keyword)) | (AdminUser.display_name.contains(keyword))
        )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    rows = (
        await db.execute(
            stmt.order_by(AdminUser.id.desc()).offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role,
                "role_label": role_display(u.role),
                "presence": u.presence,
                "capacity": u.capacity,
                "active": u.active,
                "created_at": u.created_at,
                "last_login_at": u.last_login_at,
            }
            for u in rows
        ],
    }


@router.post("/users")
async def create_user(
    body: UserCreateIn, db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_USER_ADMIN)),
):
    roles = {r.key for r in ROLE_DESC}
    if body.role not in roles:
        raise HTTPException(status_code=400, detail="非法角色")
    if len(body.username) < 3 or len(body.username) > 50:
        raise HTTPException(status_code=400, detail="用户名长度必须 3-50")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少 6 位")
    exists = (
        await db.execute(select(AdminUser).where(AdminUser.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    u = AdminUser(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        capacity=body.capacity,
        active=body.active,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return {"id": u.id}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int, body: UserUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_USER_ADMIN)),
):
    u = await db.get(AdminUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    roles = {r.key for r in ROLE_DESC}
    if body.role is not None and body.role not in roles:
        raise HTTPException(status_code=400, detail="非法角色")
    for k in ("display_name", "role", "capacity", "active"):
        v = getattr(body, k)
        if v is not None:
            setattr(u, k, v)
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail="密码长度至少 6 位")
        u.password_hash = hash_password(body.password)
    await db.commit()
    return {"ok": True}


# ---------------- 在线客服列表（供转交功能使用） ----------------

@router.get("/online-agents")
async def online_agents(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(ROLE_CAN_AGENT)),
):
    rows = (
        await db.execute(
            select(AdminUser).where(
                AdminUser.active == True,  # noqa: E712
                AdminUser.presence != "offline",
            )
        )
    ).scalars().all()
    return [
        {
            "id": u.id,
            "display_name": u.display_name or u.username,
            "role": u.role,
            "role_label": role_display(u.role),
            "presence": u.presence,
            "capacity": u.capacity,
        }
        for u in rows
    ]
