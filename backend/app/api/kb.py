"""知识库管理：FAQ / 售后政策 / 销售话术 CRUD + ES 同步"""
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import ROLE_CAN_CONFIGURE, ROLE_CAN_VIEW
from app.db.session import get_db
from app.models import KbDocument
from app.services.settings_cache import settings_cache
from app.state import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/kb", tags=["admin-kb"])

DOC_TYPES = ["faq", "policy", "script"]


class KbIn(BaseModel):
    doc_type: str
    title: str = Field(max_length=200)
    content: str | None = None  # 更新时可为空表示不修改
    category: str = Field(default="通用", max_length=50)
    tags: list[str] | None = None
    enabled: bool = True


async def _sync_kb_doc(db: AsyncSession, doc: KbDocument) -> int:
    if state.es is None or not state.es_ready:
        doc.es_synced = False
        return 0
    chunks = await state.rag.sync_kb_document(
        {
            "id": doc.id,
            "doc_type": doc.doc_type,
            "title": doc.title,
            "content": doc.content,
            "category": doc.category,
            "tags": doc.tags,
            "enabled": doc.enabled,
        }
    )
    doc.es_synced = True
    return chunks


@router.get("")
async def list_kb(
    keyword: str = "", doc_type: str = "", page: int = 1, size: int = 20,
    db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_VIEW)),
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    stmt = select(KbDocument)
    if keyword:
        stmt = stmt.where(KbDocument.title.contains(keyword))
    if doc_type:
        stmt = stmt.where(KbDocument.doc_type == doc_type)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    rows = (
        await db.execute(
            stmt.order_by(KbDocument.updated_at.desc()).offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": d.id, "doc_type": d.doc_type, "title": d.title, "category": d.category,
                "tags": d.tags, "enabled": d.enabled, "es_synced": d.es_synced,
                "content_preview": d.content[:80], "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in rows
        ],
    }


@router.post("")
async def create_kb(body: KbIn, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    if body.doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type 必须是 {DOC_TYPES}")
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    doc = KbDocument(**body.model_dump())
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    chunks = await _sync_kb_doc(db, doc)
    await db.commit()
    return {"id": doc.id, "chunks": chunks, "es_synced": doc.es_synced}


@router.get("/{doc_id}")
async def get_kb(doc_id: int, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_VIEW))):
    doc = await db.get(KbDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "id": doc.id, "doc_type": doc.doc_type, "title": doc.title,
        "content": doc.content, "category": doc.category, "tags": doc.tags,
        "enabled": doc.enabled,
    }


class KbUpdateIn(KbIn):
    if_match_updated_at: str | None = None


def _to_second_iso(dt) -> str:
    if isinstance(dt, datetime):
        return dt.replace(microsecond=0).isoformat()
    s = str(dt)
    return s.replace("Z", "+00:00").split(".")[0]


@router.put("/{doc_id}")
async def update_kb(
    doc_id: int,
    body: KbUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_role(ROLE_CAN_CONFIGURE)),
):
    from datetime import timedelta
    doc = await db.get(KbDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if body.doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type 必须是 {DOC_TYPES}")

    # 步骤① 串行：Python 层直接拿 db.get() 读到的当前值和客户端 token 做秒级比较（快路径、直接返回 409 文案）
    if body.if_match_updated_at and doc.updated_at:
        if _to_second_iso(doc.updated_at) != _to_second_iso(body.if_match_updated_at):
            raise HTTPException(status_code=409, detail="内容已被他人修改，请刷新页面后重试")

    now = datetime.now()
    payload = body.model_dump(exclude_none=True, exclude={"if_match_updated_at"})
    set_clauses = [f"{k} = :v{i}" for i, k in enumerate(payload.keys())]
    set_clauses.append("updated_at = :ts")
    params: dict = {"did": doc_id, "ts": now}
    for i, v in enumerate(payload.values()):
        params[f"v{i}"] = v
    where = ["id = :did"]
    if body.if_match_updated_at and doc.updated_at:
        # 步骤② 并发：用 BETWEEN 秒区间做 SQL 行锁判定，串行化后时间戳一定被前一个胜者写成 now → 败者区间不命中 → rowcount=0
        req_start = datetime.fromisoformat(_to_second_iso(body.if_match_updated_at))
        params["req_start"] = req_start
        params["req_end"] = req_start + timedelta(seconds=1) - timedelta(microseconds=1)
        where.append("updated_at BETWEEN :req_start AND :req_end")
    sql = f"UPDATE kb_documents SET {', '.join(set_clauses)} WHERE {' AND '.join(where)}"
    result = await db.execute(text(sql), params)
    await db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=409, detail="内容已被他人修改，请刷新页面后重试")
    await db.refresh(doc)
    chunks = await _sync_kb_doc(db, doc)
    await db.commit()
    return {
        "id": doc.id,
        "chunks": chunks,
        "es_synced": doc.es_synced,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


@router.delete("/{doc_id}")
async def delete_kb(doc_id: int, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    doc = await db.get(KbDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    await db.delete(doc)
    await db.commit()
    if state.es is not None and state.es_ready:
        await state.es.delete_kb_doc(doc_id)
    return {"ok": True}


@router.post("/{doc_id}/sync")
async def sync_kb(doc_id: int, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    if state.es is None or not state.es_ready:
        raise HTTPException(status_code=503, detail="ES 未就绪")
    doc = await db.get(KbDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    chunks = await _sync_kb_doc(db, doc)
    await db.commit()
    return {"chunks": chunks, "es_synced": True}


@router.post("/sync-all")
async def sync_all(db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    if state.es is None or not state.es_ready:
        raise HTTPException(status_code=503, detail="ES 未就绪")
    rows = (await db.execute(select(KbDocument).where(KbDocument.enabled == True))).scalars().all()  # noqa: E712
    total_chunks = 0
    for doc in rows:
        total_chunks += await _sync_kb_doc(db, doc)
    await db.commit()
    return {"synced_docs": len(rows), "total_chunks": total_chunks}
