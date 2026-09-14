"""全局配置：全部通过环境变量 / .env 覆盖，见 .env.example"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "华米商城 AI 智能客服"
    ENV: str = "dev"  # dev / prod
    SECRET_KEY: str = "please-change-me-to-a-random-64-char-string"

    # ---- LLM（OpenAI 兼容接口，默认 DeepSeek）----
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 1200
    INTENT_TEMPERATURE: float = 0.1  # 意图识别用低温度

    # ---- Embedding（向量化）----
    # provider: openai_compatible（DashScope/硅基流动/智谱等兼容接口）| local（本机 sentence-transformers）| none
    EMBEDDING_PROVIDER: str = "openai_compatible"
    EMBEDDING_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024
    EMBEDDING_BATCH_SIZE: int = 16
    EMBEDDING_DIMENSIONS_PARAM: int = 0  # 0=不传 dimensions 参数；部分模型支持自定义维度时才设置

    # ---- Elasticsearch ----
    ES_URL: str = "http://127.0.0.1:9200"
    ES_USERNAME: str = ""
    ES_PASSWORD: str = ""
    ES_INDEX_KB: str = "huami_kb"
    ES_INDEX_PRODUCTS: str = "huami_products"
    ES_REQUEST_TIMEOUT: int = 30

    # ---- RAG ----
    RAG_TOP_K: int = 6              # 每路召回条数（BM25 / 向量各一路）
    RAG_FINAL_K: int = 6            # 融合后保留条数
    RAG_MIN_SCORE: float = 0.005    # RRF 融合分低于此值视为无效召回
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 100

    # ---- 数据库 ----
    DATABASE_URL: str = "mysql+aiomysql://huami:huami123@127.0.0.1:3306/huami_agent?charset=utf8mb4"
    # ---- 限流：留空=内存桶（单 worker），有值=Redis Lua 滑动窗口（多 worker）----
    REDIS_URL: str = ""

    # ---- 业务参数 ----
    HISTORY_TURNS: int = 12              # 携带的历史消息条数
    RATE_LIMIT_PER_MIN: int = 30         # 单 IP 每分钟聊天请求上限
    ADMIN_TOKEN_EXPIRE_HOURS: int = 12
    CORS_ORIGINS: str = "*"              # 生产环境务必改成商城域名，逗号分隔
    HUMAN_HANDOFF_KEYWORDS: str = "人工,真人,客服人员,转接人工,投诉到哪,打电话"

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENV == "prod":
            if self.SECRET_KEY == "please-change-me-to-a-random-64-char-string":
                raise ValueError("生产环境必须配置非默认 SECRET_KEY")
            if self.CORS_ORIGINS.strip() == "*":
                raise ValueError("生产环境必须配置明确的 CORS_ORIGINS")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def handoff_keywords_list(self) -> list[str]:
        return [k.strip() for k in self.HUMAN_HANDOFF_KEYWORDS.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
