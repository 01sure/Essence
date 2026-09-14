"""向量化服务（可插拔）：
- openai_compatible: 兼容硅基流动 / DashScope / 智谱等 OpenAI 风格 embedding 接口
- local: 本机 sentence-transformers（可选依赖）
- none: 禁用（纯 BM25 检索）
"""
import asyncio
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None  # 懒加载
        self._local_model = None

    @property
    def enabled(self) -> bool:
        return self.settings.EMBEDDING_PROVIDER != "none"

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            s = self.settings
            self._client = AsyncOpenAI(
                base_url=s.EMBEDDING_BASE_URL, api_key=s.EMBEDDING_API_KEY, timeout=30
            )
        return self._client

    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("加载本地向量化模型 %s ...", self.settings.EMBEDDING_MODEL)
            self._local_model = SentenceTransformer(self.settings.EMBEDDING_MODEL)
        return self._local_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，自动分批；失败时返回空列表列表以便调用方降级为纯 BM25"""
        if not texts:
            return []
        if not self.enabled:
            return [[] for _ in texts]

        s = self.settings
        try:
            if s.EMBEDDING_PROVIDER == "local":
                model = self._get_local_model()
                vectors = await asyncio.to_thread(
                    model.encode, texts, normalize_embeddings=True
                )
                return [v.tolist() for v in vectors]

            result: list[list[float]] = []
            batch_size = max(1, s.EMBEDDING_BATCH_SIZE)
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                kwargs: dict = {"model": s.EMBEDDING_MODEL, "input": batch}
                if s.EMBEDDING_DIMENSIONS_PARAM > 0:
                    kwargs["dimensions"] = s.EMBEDDING_DIMENSIONS_PARAM
                resp = await self._get_client().embeddings.create(**kwargs)
                result.extend([d.embedding for d in resp.data])
            return result
        except Exception:
            logger.exception("向量化失败，本次检索将降级为纯关键词")
            return [[] for _ in texts]

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0] if vectors and vectors[0] else []


embedding_service = EmbeddingService()
