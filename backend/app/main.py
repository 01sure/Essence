"""应用入口：python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    analytics,
    auth,
    after_sale,
    chat,
    kb,
    products,
    sessions,
    settings as settings_api,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine
from app.state import state

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]  # 项目根目录


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging("DEBUG" if get_settings().ENV == "dev" else "INFO")
    # 1. 建表（生产建议迁移工具管理）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text

        # 兼容：升级老库（SQLite/MySQL 通用 ADD COLUMN IF NOT EXISTS 风格通过 try/except 保证幂等）
        migrations = [
            # admin_users 新增字段
            "ALTER TABLE admin_users ADD COLUMN presence VARCHAR(16) NOT NULL DEFAULT 'offline'",
            "ALTER TABLE admin_users ADD COLUMN capacity INTEGER NOT NULL DEFAULT 8",
            "ALTER TABLE admin_users ADD COLUMN active TINYINT NOT NULL DEFAULT 1",
            "ALTER TABLE admin_users ADD COLUMN presence_updated_at DATETIME",
            # chat_sessions 新增字段（兼容 user_ip 历史 NOT NULL 列 + 新 ua/ip 列）
            "ALTER TABLE chat_sessions ADD COLUMN user_ip VARCHAR(64) NOT NULL DEFAULT ''",
            "ALTER TABLE chat_sessions ADD COLUMN ua VARCHAR(500) NOT NULL DEFAULT ''",
            "ALTER TABLE chat_sessions ADD COLUMN ip VARCHAR(64) NOT NULL DEFAULT ''",
            "ALTER TABLE chat_sessions ADD COLUMN intent_last VARCHAR(30) NOT NULL DEFAULT ''",
            "ALTER TABLE chat_sessions ADD COLUMN human_admin_id INTEGER",
            "ALTER TABLE chat_sessions ADD COLUMN assigned_at DATETIME",
            "ALTER TABLE chat_sessions ADD COLUMN quality_score INTEGER",
            "ALTER TABLE chat_sessions ADD COLUMN quality_admin_id INTEGER",
            "ALTER TABLE chat_sessions ADD COLUMN quality_remark VARCHAR(500) NOT NULL DEFAULT ''",
            "ALTER TABLE chat_sessions ADD COLUMN quality_created_at DATETIME",
            "ALTER TABLE chat_sessions ADD COLUMN meta TEXT",
        ]
        for ddl in migrations:
            try:
                await conn.execute(text(ddl))
            except Exception:
                # 列已存在（SQLite duplicate column / MySQL duplicate column）
                pass
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_after_sale_tickets_status "
                "ON after_sale_tickets (status)"
            ))
        except Exception:
            pass
        try:
            # (session_id, seq) 唯一索引：先清理重复再建
            await conn.execute(text(
                "DELETE FROM chat_messages WHERE id NOT IN "
                "(SELECT MIN(id) FROM chat_messages GROUP BY session_id, seq)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_messages_session_seq "
                "ON chat_messages (session_id, seq)"
            ))
        except Exception:
            logger.warning("chat_messages 唯一索引补建失败（可能已存在）", exc_info=True)
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_users_role ON admin_users (role)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_sessions_human_admin_id ON chat_sessions (human_admin_id)"))
        except Exception:
            pass
    logger.info("数据库表已就绪（DDL 升级兼容）")

    # 2. 初始化 ES / RAG / Agent
    from app.services.agent import build_agent
    from app.services.es_client import ESService
    from app.services.rag import RAGService

    es = ESService()
    state.es = es
    state.rag = RAGService(es)
    state.agent = build_agent(state.rag)
    try:
        await es.ensure_indices()
        state.es_ready = True
        logger.info("Elasticsearch 就绪（分词器: %s）", es.analyzer)
    except Exception as exc:
        logger.warning("Elasticsearch 未就绪，检索将不可用: %s", exc)
    yield
    try:
        await es.client.close()
    except Exception:
        pass


app = FastAPI(title=get_settings().APP_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(kb.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(after_sale.router)
app.include_router(settings_api.router, prefix="/api")


@app.get("/api/health")
async def health():
    s = get_settings()
    dependencies_ready = state.es_ready and bool(s.LLM_API_KEY)
    return {
        "ok": dependencies_ready,
        "status": "healthy" if dependencies_ready else "degraded",
        "es_ready": state.es_ready,
        "llm_configured": bool(s.LLM_API_KEY),
        "embedding_provider": s.EMBEDDING_PROVIDER,
        "embedding_ready": bool(s.EMBEDDING_API_KEY) or s.EMBEDDING_PROVIDER == "local",
    }


# 开发环境静态托管：widget 演示页与管理后台构建产物（生产由 nginx 托管）
_widget_dir = ROOT_DIR / "frontend" / "widget"
if _widget_dir.exists():
    app.mount("/widget", StaticFiles(directory=str(_widget_dir), html=True), name="widget")
_admin_dist = ROOT_DIR / "frontend" / "admin" / "dist"
if _admin_dist.exists():
    app.mount("/admin", StaticFiles(directory=str(_admin_dist), html=True), name="admin")
