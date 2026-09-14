"""商品管理：CRUD、批量导入、ES 同步"""
import csv
import io
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.roles import ROLE_CAN_CONFIGURE, ROLE_CAN_VIEW
from app.db.session import get_db
from app.models import Product
from app.state import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/products", tags=["admin-products"])


class ProductIn(BaseModel):
    name: str
    brand: str = "Amazfit"
    category: str = "智能手表"
    price: float
    original_price: float | None = None
    stock: int = 0
    sales: int = 0
    rating: float = 4.8
    tags: list[str] | None = None
    description: str = ""
    selling_points: list[str] | None = None
    url: str = ""
    image_url: str = ""
    enabled: bool = True


async def _sync_product(db: AsyncSession, product: Product) -> bool:
    if state.es is None or not state.es_ready:
        product.es_synced = False
        return False
    await state.rag.sync_product(
        {
            "id": product.id, "name": product.name, "brand": product.brand,
            "category": product.category, "price": float(product.price),
            "original_price": float(product.original_price) if product.original_price else None,
            "stock": product.stock, "sales": product.sales, "rating": float(product.rating),
            "tags": product.tags, "description": product.description,
            "selling_points": product.selling_points, "url": product.url,
            "image_url": product.image_url, "enabled": product.enabled,
        }
    )
    product.es_synced = True
    return True


@router.get("")
async def list_products(
    keyword: str = "", category: str = "", page: int = 1, size: int = 20,
    db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_VIEW)),
):
    stmt = select(Product)
    if keyword:
        stmt = stmt.where(Product.name.contains(keyword))
    if category:
        stmt = stmt.where(Product.category == category)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    rows = (
        await db.execute(
            stmt.order_by(Product.sales.desc()).offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": p.id, "name": p.name, "brand": p.brand, "category": p.category,
                "price": float(p.price), "original_price": float(p.original_price) if p.original_price else None,
                "stock": p.stock, "sales": p.sales, "rating": float(p.rating),
                "tags": p.tags, "description": p.description, "selling_points": p.selling_points,
                "url": p.url, "image_url": p.image_url, "enabled": p.enabled,
                "es_synced": p.es_synced,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ],
    }


@router.post("")
async def create_product(body: ProductIn, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    product = Product(**body.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    await _sync_product(db, product)
    await db.commit()
    return {"id": product.id, "es_synced": product.es_synced}


class ProductUpdateIn(ProductIn):
    """编辑商品时可附带 if_match_updated_at 做乐观锁，避免多人同时保存互相覆盖。
    if_match_updated_at 传前端打开编辑面板时拿到的 updated_at（秒级 ISO 字符串，忽略毫秒/时区差异）。"""
    if_match_updated_at: str | None = None


def _to_second_iso(dt) -> str:
    if isinstance(dt, datetime):
        return dt.replace(microsecond=0).isoformat()
    s = str(dt)
    return s.replace("Z", "+00:00").split(".")[0]


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    body: ProductUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_role(ROLE_CAN_CONFIGURE)),
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    # ---- 乐观锁 ----
    # 步骤① 串行场景：在 Python 层把客户端读取时 token 与 DB 当前值按「秒级」先做一次比对。
    #        同一用户开两个编辑窗连续保存，只要前一次提交已经把 updated_at 改了，这里直接 409。
    if body.if_match_updated_at and product.updated_at:
        if _to_second_iso(product.updated_at) != _to_second_iso(body.if_match_updated_at):
            raise HTTPException(status_code=409, detail="内容已被他人修改，请刷新页面后重试")
    # 步骤② 并发场景：UPDATE 语句本身再做一次 updated_at == token 的 SQL 行锁比较，
    #        并同时强制写 updated_at = NOW()，保证胜者一定改时间戳、败者 rowcount=0 -> 409。
    now = datetime.now()
    payload = body.model_dump(exclude={"if_match_updated_at"})
    set_clauses = [f"{k} = :v{i}" for i, k in enumerate(payload.keys())]
    set_clauses.append("updated_at = :ts")
    params: dict = {"pid": product_id, "ts": now}
    for i, v in enumerate(payload.values()):
        params[f"v{i}"] = v
    where = ["id = :pid"]
    if body.if_match_updated_at and product.updated_at:
        # ① SQL 层真正的「DB 行当前最新值」比对：不同方言用各自的"秒级截断"
        #    SQLite: strftime('%Y-%m-%d %H:%M:%S', updated_at)
        #    MySQL:  DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s')
        #    通过把 engine 方言名绑定 + CASE WHEN 路由；简单起见，两端都支持的 INSTR 替代方案：
        #    WHERE updated_at BETWEEN :req_start AND :req_end。
        # 用 req_second 转成 datetime 再取「该秒区间」做 BETWEEN，完全方言无关且走索引友好。
        req_dt_s = _to_second_iso(body.if_match_updated_at)
        try:
            req_start = datetime.fromisoformat(req_dt_s)
        except ValueError:  # 非法格式 -> 交给 Python 层先前已经抛的兜底，实际上前面已经比对过
            req_start = product.updated_at.replace(microsecond=0)
        # 边界：[当前秒, 当前秒+1s-1ms]
        req_end_str = req_start.replace(microsecond=0)
        from datetime import timedelta
        req_end = req_start + timedelta(seconds=1) - timedelta(microseconds=1)
        params["req_start"] = req_start
        params["req_end"] = req_end
        # 注意：SQLite 原生 DATETIME 列和 Python datetime 绑定参数的比较是「值比较」，行级一致；
        #       这里一定比较 updated_at 列而非 Python 缓存值，才能保证并发下 SQL 层串行后的胜负。
        where.append("updated_at BETWEEN :req_start AND :req_end")
    sql = f"UPDATE products SET {', '.join(set_clauses)} WHERE {' AND '.join(where)}"
    result = await db.execute(text(sql), params)
    await db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=409, detail="内容已被他人修改，请刷新页面后重试")
    await db.refresh(product)
    await _sync_product(db, product)
    await db.commit()
    return {
        "id": product.id,
        "es_synced": product.es_synced,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


@router.delete("/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    await db.delete(product)
    await db.commit()
    if state.es is not None and state.es_ready:
        await state.es.delete_product(product_id)
    return {"ok": True}


@router.post("/import")
async def import_products(
    file: UploadFile | None = None, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))
):
    """
    支持 JSON（数组）或 CSV（表头：name,category,price,stock,selling_points(|分隔),tags(|分隔),description,url,image_url）
    """
    if file is None:
        raise HTTPException(status_code=400, detail="请上传文件")
    raw = await file.read()
    text = raw.decode("utf-8-sig")
    rows: list[dict] = []
    try:
        if text.lstrip().startswith("["):
            rows = json.loads(text)
        else:
            reader = csv.DictReader(io.StringIO(text))
            for r in reader:
                r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k}
                if r.get("selling_points"):
                    r["selling_points"] = [x for x in r["selling_points"].split("|") if x]
                if r.get("tags"):
                    r["tags"] = [x for x in r["tags"].split("|") if x]
                rows.append(r)
    except Exception:
        raise HTTPException(status_code=400, detail="文件解析失败，请检查格式")

    created, errors = 0, []
    for i, r in enumerate(rows):
        try:
            product = Product(
                name=str(r["name"]),
                brand=r.get("brand", "Amazfit"),
                category=r.get("category", "智能手表"),
                price=float(r["price"]),
                original_price=float(r["original_price"]) if r.get("original_price") else None,
                stock=int(r.get("stock", 0)),
                sales=int(r.get("sales", 0)),
                rating=float(r.get("rating", 4.8)),
                tags=r.get("tags") or [],
                description=r.get("description", ""),
                selling_points=r.get("selling_points") or [],
                url=r.get("url", ""),
                image_url=r.get("image_url", ""),
            )
            db.add(product)
            await db.commit()
            await db.refresh(product)
            await _sync_product(db, product)
            await db.commit()
            created += 1
        except Exception:
            errors.append(f"第{i + 1}行导入失败")
    return {"created": created, "errors": errors}


@router.post("/sync-all")
async def sync_all(db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    if state.es is None or not state.es_ready:
        raise HTTPException(status_code=503, detail="ES 未就绪")
    rows = (await db.execute(select(Product).where(Product.enabled == True))).scalars().all()  # noqa: E712
    for product in rows:
        await _sync_product(db, product)
    await db.commit()
    return {"synced": len(rows)}


@router.post("/{product_id}/sync")
async def sync_product(product_id: int, db: AsyncSession = Depends(get_db), _: object = Depends(require_role(ROLE_CAN_CONFIGURE))):
    if state.es is None or not state.es_ready:
        raise HTTPException(status_code=503, detail="ES 未就绪")
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    await _sync_product(db, product)
    await db.commit()
    return {"es_synced": True}
