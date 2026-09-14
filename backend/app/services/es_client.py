"""Elasticsearch 客户端：索引管理、中文分词探测、混合检索（BM25 + kNN）、RRF 融合"""
import logging
from typing import Any

from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings
from app.services.embeddings import embedding_service

logger = logging.getLogger(__name__)


class ESService:
    def __init__(self) -> None:
        self.settings = get_settings()
        s = self.settings
        auth = (s.ES_USERNAME, s.ES_PASSWORD) if s.ES_USERNAME else None
        self.client = AsyncElasticsearch(
            s.ES_URL,
            basic_auth=auth,
            request_timeout=s.ES_REQUEST_TIMEOUT,
            retry_on_timeout=True,
            max_retries=2,
        )
        self.analyzer: str = "standard"  # 启动时探测，有 IK 则用 IK

    @property
    def available(self) -> bool:
        return self.client is not None

    # ---------- 索引管理 ----------

    def _kb_mappings(self) -> dict:
        s = self.settings
        return {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {},
            },
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "chunk_id": {"type": "integer"},
                    "doc_type": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": self.analyzer},
                    "content": {"type": "text", "analyzer": self.analyzer},
                    "category": {"type": "keyword"},
                    "tags": {"type": "text", "analyzer": self.analyzer},
                    "enabled": {"type": "boolean"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": s.EMBEDDING_DIM,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        }

    def _product_mappings(self) -> dict:
        s = self.settings
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "product_id": {"type": "integer"},
                    "name": {"type": "text", "analyzer": self.analyzer},
                    "brand": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "price": {"type": "float"},
                    "original_price": {"type": "float"},
                    "stock": {"type": "integer"},
                    "sales": {"type": "integer"},
                    "rating": {"type": "float"},
                    "tags": {"type": "text", "analyzer": self.analyzer},
                    "description": {"type": "text", "analyzer": self.analyzer},
                    "selling_points": {"type": "text", "analyzer": self.analyzer},
                    "url": {"type": "keyword"},
                    "image_url": {"type": "keyword"},
                    "enabled": {"type": "boolean"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": s.EMBEDDING_DIM,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        }

    async def detect_analyzer(self) -> None:
        """探测 IK 分词是否可用，否则退回 standard"""
        try:
            await self.client.indices.analyze(analyzer="ik_max_word", text="华米智能手表")
            self.analyzer = "ik_max_word"
        except Exception:
            self.analyzer = "standard"
        logger.info("ES 分词器: %s", self.analyzer)

    async def ensure_indices(self) -> None:
        await self.detect_analyzer()
        for name, mappings in (
            (self.settings.ES_INDEX_KB, self._kb_mappings()),
            (self.settings.ES_INDEX_PRODUCTS, self._product_mappings()),
        ):
            exists = await self.client.indices.exists(index=name)
            if not exists:
                await self.client.indices.create(index=name, **mappings)
                logger.info("已创建索引 %s", name)

    async def recreate_index(self, index: str) -> None:
        if await self.client.indices.exists(index=index):
            await self.client.indices.delete(index=index)
        mappings = (
            self._kb_mappings()
            if index == self.settings.ES_INDEX_KB
            else self._product_mappings()
        )
        await self.client.indices.create(index=index, **mappings)

    # ---------- 写入 ----------

    async def index_kb_chunks(self, doc_id: int, chunks: list[dict]) -> None:
        """chunks: [{chunk_id, title, content, doc_type, category, tags, embedding}]"""
        await self.client.delete_by_query(
            index=self.settings.ES_INDEX_KB, query={"term": {"doc_id": doc_id}}, refresh=True
        )
        if not chunks:
            return
        actions = []
        for c in chunks:
            actions.append({"index": {"_index": self.settings.ES_INDEX_KB}})
            actions.append(c)
        await self.client.bulk(operations=actions, refresh=True)

    async def delete_kb_doc(self, doc_id: int) -> None:
        await self.client.delete_by_query(
            index=self.settings.ES_INDEX_KB, query={"term": {"doc_id": doc_id}}, refresh=True
        )

    async def index_product(self, doc: dict) -> None:
        pid = doc["product_id"]
        await self.client.delete_by_query(
            index=self.settings.ES_INDEX_PRODUCTS,
            query={"term": {"product_id": pid}},
            refresh=True,
        )
        if doc.get("embedding"):
            await self.client.index(
                index=self.settings.ES_INDEX_PRODUCTS,
                id=pid,
                document=doc,
                refresh=True,
            )

    async def delete_product(self, product_id: int) -> None:
        await self.client.delete_by_query(
            index=self.settings.ES_INDEX_PRODUCTS,
            query={"term": {"product_id": product_id}},
            refresh=True,
        )

    # ---------- 检索 ----------

    async def _bm25_kb(self, query: str, doc_types: list[str] | None, top_k: int) -> list[dict]:
        filters: list[dict] = [{"term": {"enabled": True}}]
        if doc_types:
            filters.append({"terms": {"doc_type": doc_types}})
        body: dict[str, Any] = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^3", "content", "category^2", "tags^2"],
                            "type": "best_fields",
                        }
                    },
                    "filter": filters,
                }
            },
            "source": ["doc_id", "chunk_id", "doc_type", "title", "content", "category", "tags"],
        }
        resp = await self.client.search(index=self.settings.ES_INDEX_KB, **body)
        return [
            {"score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]
        ]

    async def _knn_kb(self, query: str, doc_types: list[str] | None, top_k: int) -> list[dict]:
        vector = await embedding_service.embed_one(query)
        if not vector:
            return []
        filters: list[dict] = [{"term": {"enabled": True}}]
        if doc_types:
            filters.append({"terms": {"doc_type": doc_types}})
        body: dict[str, Any] = {
            "size": top_k,
            "knn": {
                "field": "embedding",
                "query_vector": vector,
                "k": top_k,
                "num_candidates": top_k * 5,
                "filter": filters,
            },
            "source": ["doc_id", "chunk_id", "doc_type", "title", "content", "category", "tags"],
        }
        resp = await self.client.search(index=self.settings.ES_INDEX_KB, **body)
        return [
            {"score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]
        ]

    async def _bm25_products(self, query: str, top_k: int) -> list[dict]:
        body: dict[str, Any] = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "name^4",
                                "tags^3",
                                "selling_points^2",
                                "description",
                                "category^2",
                            ],
                            "type": "best_fields",
                        }
                    },
                    "filter": [{"term": {"enabled": True}}],
                }
            },
            "source": [
                "product_id", "name", "brand", "category", "price", "original_price",
                "stock", "sales", "rating", "tags", "selling_points", "url", "image_url",
            ],
        }
        resp = await self.client.search(index=self.settings.ES_INDEX_PRODUCTS, **body)
        return [{"score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]

    async def _knn_products(self, query: str, top_k: int) -> list[dict]:
        vector = await embedding_service.embed_one(query)
        if not vector:
            return []
        body: dict[str, Any] = {
            "size": top_k,
            "knn": {
                "field": "embedding",
                "query_vector": vector,
                "k": top_k,
                "num_candidates": top_k * 5,
                "filter": [{"term": {"enabled": True}}],
            },
            "source": [
                "product_id", "name", "brand", "category", "price", "original_price",
                "stock", "sales", "rating", "tags", "selling_points", "url", "image_url",
            ],
        }
        resp = await self.client.search(index=self.settings.ES_INDEX_PRODUCTS, **body)
        return [{"score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]

    async def search_kb(
        self, query: str, doc_types: list[str] | None = None, top_k: int | None = None
    ) -> list[dict]:
        """知识库混合检索（BM25 + 向量 RRF 融合）"""
        s = self.settings
        k = top_k or s.RAG_FINAL_K
        try:
            bm25_task = self._bm25_kb(query, doc_types, s.RAG_TOP_K)
            knn_task = self._knn_kb(query, doc_types, s.RAG_TOP_K)
            bm25_hits, knn_hits = await _gather(bm25_task, knn_task)
            return rrf_fuse([bm25_hits, knn_hits], k, s.RAG_MIN_SCORE)
        except Exception:
            logger.exception("知识库检索失败")
            return []

    async def search_products(self, query: str, top_k: int | None = None) -> list[dict]:
        s = self.settings
        k = top_k or s.RAG_FINAL_K
        try:
            bm25_task = self._bm25_products(query, s.RAG_TOP_K)
            knn_task = self._knn_products(query, s.RAG_TOP_K)
            bm25_hits, knn_hits = await _gather(bm25_task, knn_task)
            return rrf_fuse([bm25_hits, knn_hits], k, s.RAG_MIN_SCORE)
        except Exception:
            logger.exception("商品检索失败")
            return []


async def _gather(*aws):
    """并发执行，单个失败不拖垮另一路"""
    import asyncio

    results = await asyncio.gather(*aws, return_exceptions=True)
    return [r if not isinstance(r, Exception) else [] for r in results]


def rrf_fuse(hit_lists: list[list[dict]], top_k: int, min_score: float = 0.0) -> list[dict]:
    """Reciprocal Rank Fusion：对多路召回按排名融合"""
    s = get_settings()
    k = 60
    fused: dict[str, dict] = {}
    for hits in hit_lists:
        for rank, hit in enumerate(hits):
            key = f"{hit.get('doc_id', hit.get('product_id'))}-{hit.get('chunk_id', 0)}"
            gain = 1.0 / (k + rank + 1)
            if key in fused:
                fused[key]["rrf_score"] += gain
            else:
                fused[key] = {"rrf_score": gain, **hit}
    out = sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)
    return [h for h in out if h["rrf_score"] >= min_score][:top_k] if min_score > 0 else out[:top_k]
