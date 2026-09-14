"""系统设置：人设/话术/规则/敏感词（管理后台可编辑）"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import ROLE_CAN_CONFIGURE, ROLE_CAN_VIEW
from app.db.session import get_db
from app.models import Setting
from app.services.settings_cache import settings_cache

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


class SettingIn(BaseModel):
    value: Any
    if_match_updated_at: str | None = None

# 允许后台编辑的键
ALLOWED_KEYS = {
    "persona": "品牌人设",
    "sales_playbook": "销售话术规范",
    "intent_rules": "意图话术规则（JSON）",
    "human_handoff_message": "转人工提示语",
    "fallback_message": "AI 失败兜底语",
    "sensitive_reply": "敏感词拦截回复",
    "opening_greeting": "开场白",
    "sensitive_words": "敏感词列表（JSON 数组）",
}


@router.get("")
async def get_settings_all(db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_VIEW))):
    rows = await _all_rows(db)
    return {
        "items": [
            {
                "key": key,
                "label": ALLOWED_KEYS.get(key, key),
                "value": value,
                "updated_at": updated_at.isoformat() if updated_at else None,
            }
            for key, value, updated_at in rows
        ]
    }


async def _all_rows(db: AsyncSession):
    from sqlalchemy import select

    result = await db.execute(select(Setting).where(Setting.key.in_(ALLOWED_KEYS.keys())))
    existing = {r.key: (r.value, r.updated_at) for r in result.scalars().all()}
    return [(k, *existing.get(k, (None, None))) for k in ALLOWED_KEYS]


@router.put("/{key}")
async def update_setting(
    key: str,
    body: SettingIn,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_role(ROLE_CAN_CONFIGURE)),
):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail="不允许的配置键")
    row = await db.get(Setting, key)
    # 乐观锁：仅当 key 已存在且前端传了 if_match_updated_at 时才比对
    if row and body.if_match_updated_at and row.updated_at:
        def _to_second_iso(dt) -> str:
            if isinstance(dt, datetime):
                return dt.replace(microsecond=0).isoformat()
            s = str(dt)
            return s.replace("Z", "+00:00").split(".")[0]

        if _to_second_iso(row.updated_at) != _to_second_iso(body.if_match_updated_at):
            raise HTTPException(status_code=409, detail="内容已被他人修改，请刷新页面后重试")

    if row:
        row.value = body.value
    else:
        db.add(Setting(key=key, value=body.value))
    await db.commit()
    await db.refresh(row) if row else None
    settings_cache.invalidate()
    return {
        "ok": True,
        "updated_at": (row.updated_at.isoformat() if row and row.updated_at else None),
    }
