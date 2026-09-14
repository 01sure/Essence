"""数据看板"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import ROLE_CAN_ANALYZE
from app.db.session import get_db
from app.services import analytics

router = APIRouter(prefix="/admin", tags=["admin-analytics"])


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_ANALYZE))):
    return await analytics.dashboard_stats(db)
