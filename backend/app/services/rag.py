"""RAG：文档分块、向量化索引、上下文组装"""
import logging
import re

from app.core.config import get_settings
from app.services.embeddings import embedding_service
from app.services.es_client import ESService

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    """按段落/句子边界递归分块，带重叠窗口"""
    s = get_settings()
    size = chunk_size or s.CHUNK_SIZE
    overlap = overlap if overlap is not None else s.CHUNK_OVERLAP
    text = re.sub(r"\r\n", "\n", text).strip()
    if len(text) <= size:
        return [text] if text else []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        # 单段超长时按句子切
        if len(para) > size:
            sentences = re.split(r"(?<=[。！？!?；;])", para)
            for sent in sentences:
                if not sent:
                    continue
                if len(buf) + len(sent) > size and buf:
                    chunks.append(buf)
                    buf = buf[-overlap:] if overlap < len(buf) else buf
                buf += sent
        else:
            if len(buf) + len(para) > size and buf:
                chunks.append(buf)
                buf = buf[-overlap:] if overlap < len(buf) else buf
            buf = f"{buf}\n{para}" if buf else para
    if buf.strip():
        chunks.append(buf)
    return [c.strip() for c in chunks if c.strip()]


def product_text_for_embedding(p: dict) -> str:
    """商品索引文本：名称 + 卖点 + 标签 + 描述"""
    parts = [p.get("name", ""), p.get("brand", ""), p.get("category", "")]
    parts += p.get("tags") or []
    parts += p.get("selling_points") or []
    parts.append(p.get("description", ""))
    return " ".join(str(x) for x in parts if x)


class RAGService:
    def __init__(self, es: ESService) -> None:
        self.es = es

    async def sync_kb_document(self, doc: dict) -> int:
        """将知识库文档分块、向量化并写入 ES，返回块数"""
        chunks = chunk_text(doc["content"])
        if not chunks:
            await self.es.index_kb_chunks(doc["id"], [])
            return 0
        embeddings = await embedding_service.embed(chunks)
        payload = [
            {
                "doc_id": doc["id"],
                "chunk_id": i,
                "doc_type": doc["doc_type"],
                "title": doc["title"],
                "content": c,
                "category": doc.get("category", "通用"),
                "tags": doc.get("tags") or [],
                "enabled": bool(doc.get("enabled", True)),
                "embedding": embeddings[i] if i < len(embeddings) else [],
            }
            for i, c in enumerate(chunks)
        ]
        await self.es.index_kb_chunks(doc["id"], payload)
        return len(payload)

    async def sync_product(self, product: dict) -> None:
        text = product_text_for_embedding(product)
        vector = await embedding_service.embed_one(text) if text else []
        doc = {
            "product_id": product["id"],
            "name": product["name"],
            "brand": product.get("brand", ""),
            "category": product.get("category", ""),
            "price": float(product.get("price") or 0),
            "original_price": float(product["original_price"]) if product.get("original_price") else None,
            "stock": int(product.get("stock") or 0),
            "sales": int(product.get("sales") or 0),
            "rating": float(product.get("rating") or 4.8),
            "tags": product.get("tags") or [],
            "description": product.get("description", ""),
            "selling_points": product.get("selling_points") or [],
            "url": product.get("url", ""),
            "image_url": product.get("image_url", ""),
            "enabled": bool(product.get("enabled", True)),
            "embedding": vector,
        }
        await self.es.index_product(doc)

    async def retrieve_context(self, query: str, intent: str) -> tuple[str, list[dict]]:
        """
        按意图检索并组装上下文。
        返回 (context_text, product_cards)
        """
        context_parts: list[str] = []
        cards: list[dict] = []

        if intent in ("pre_sale", "complaint"):
            kb_hits = await self.es.search_kb(
                query, doc_types=["faq", "policy", "script"] if intent == "pre_sale" else ["policy"]
            )
            if kb_hits:
                lines = [
                    f"[{h.get('doc_type', 'kb')}#{h.get('doc_id')}·{h.get('title', '')}] {h.get('content', '')}"
                    for h in kb_hits
                ]
                context_parts.append("【知识库参考资料】\n" + "\n---\n".join(lines))

        if intent == "pre_sale":
            product_hits = await self.es.search_products(query)
            cards = [
                {
                    "product_id": h.get("product_id"),
                    "name": h.get("name"),
                    "price": h.get("price"),
                    "original_price": h.get("original_price"),
                    "stock": h.get("stock"),
                    "sales": h.get("sales"),
                    "rating": h.get("rating"),
                    "tags": h.get("tags") or [],
                    "selling_points": (h.get("selling_points") or [])[:3],
                    "url": h.get("url", ""),
                    "image_url": h.get("image_url", ""),
                }
                for h in product_hits
            ]
            if product_hits:
                lines = []
                for h in product_hits:
                    pts = "；".join((h.get("selling_points") or [])[:3])
                    lines.append(
                        f"- {h.get('name')}（{h.get('brand')}）¥{h.get('price')} 库存{h.get('stock')} "
                        f"月销{h.get('sales')} 评分{h.get('rating')}｜卖点：{pts}"
                    )
                context_parts.append("【候选商品（可推荐，禁止编造价格与库存）】\n" + "\n".join(lines))

        return ("\n\n".join(context_parts), cards[:3])


def build_rag(es: ESService) -> RAGService:
    return RAGService(es)
