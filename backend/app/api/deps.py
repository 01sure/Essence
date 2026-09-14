"""公共依赖：管理员鉴权 + 角色守卫 + 限流（内存/Redis 可切换）"""
from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import ROLE_CAN_VIEW, ALL_ROLES, has_any_role
from app.core.security import decode_admin_token
from app.db.session import get_db
from app.models import AdminUser
from app.services.rate_limiter import rate_check

_bearer = HTTPBearer(auto_error=False)


async def chat_rate_limit(request: Request) -> None:
    ok = await rate_check(client_ip(request))
    if not ok:
        raise HTTPException(status_code=429, detail="请求太频繁，请稍后再试")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_admin_from_token(
    credentials: HTTPAuthorizationCredentials | None, db: AsyncSession
) -> AdminUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_admin_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    try:
        admin_id = int(payload.get("sub", 0))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="token 无效") from exc
    admin = await db.get(AdminUser, admin_id)
    if admin is None or not admin.active:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return admin


def require_role(allowed_roles: Iterable[str] | str | None = None):
    """
    角色守卫装饰器：
      require_role()                          => 任意已登录后台账号（默认包含 analyst）
      require_role("agent")                   => 单一角色
      require_role(ROLE_CAN_AGENT)            => 角色元组
    super_admin 永远放行。
    """
    if isinstance(allowed_roles, str):
        allowed: tuple[str, ...] = (allowed_roles,)
    elif allowed_roles is None:
        allowed = tuple(ALL_ROLES)  # 默认：任意已登录后台账号（含 analyst）
    else:
        allowed = tuple(allowed_roles)

    async def dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: AsyncSession = Depends(get_db),
    ) -> AdminUser:
        admin = await _get_admin_from_token(credentials, db)
        if not has_any_role(admin.role, allowed):
            raise HTTPException(status_code=403, detail="权限不足")
        return admin

    return dep


# 兼容旧 API：require_admin 作为默认登录守卫
require_admin = require_role(ROLE_CAN_VIEW)
