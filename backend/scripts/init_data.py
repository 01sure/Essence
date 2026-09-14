"""初始化数据：建表、管理员账号、种子商品/知识库/订单/系统设置，并尝试同步 ES。

用法（在 backend 目录下）：
    python scripts/init_data.py
可选环境变量：ADMIN_USERNAME（默认 admin）、ADMIN_PASSWORD（默认 admin123）
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

import os

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.roles import (
    ROLE_ADMIN,
    ROLE_AGENT,
    ROLE_ANALYST,
    ROLE_SUPER_ADMIN,
    ROLE_TEAM_LEADER,
)
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import AdminUser, KbDocument, Order, Product, Setting
from app.services.agent import (
    DEFAULT_FALLBACK,
    DEFAULT_GREETING,
    DEFAULT_HANDOFF_MESSAGE,
    DEFAULT_INTENT_RULES,
    DEFAULT_PERSONA,
    DEFAULT_PLAYBOOK,
    DEFAULT_SENSITIVE_REPLY,
)

setup_logging("INFO")

SEEDS_DIR = Path(__file__).resolve().parents[1] / "app" / "seeds"

DEFAULT_SETTINGS = {
    "persona": DEFAULT_PERSONA,
    "sales_playbook": DEFAULT_PLAYBOOK,
    "intent_rules": DEFAULT_INTENT_RULES,
    "human_handoff_message": DEFAULT_HANDOFF_MESSAGE,
    "fallback_message": DEFAULT_FALLBACK,
    "sensitive_reply": DEFAULT_SENSITIVE_REPLY,
    "opening_greeting": DEFAULT_GREETING,
    "sensitive_words": ["自杀", "色情", "赌博", "洗钱", "发票代开"],
}


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text

        # 兼容老库（SQLite/MySQL）：幂等 ADD COLUMN
        migrations = [
            "ALTER TABLE admin_users ADD COLUMN presence VARCHAR(16) NOT NULL DEFAULT 'offline'",
            "ALTER TABLE admin_users ADD COLUMN capacity INTEGER NOT NULL DEFAULT 8",
            "ALTER TABLE admin_users ADD COLUMN active TINYINT NOT NULL DEFAULT 1",
            "ALTER TABLE admin_users ADD COLUMN presence_updated_at DATETIME",
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
                pass
        try:
            await conn.execute(text(
                "DELETE FROM chat_messages WHERE id NOT IN "
                "(SELECT MIN(id) FROM chat_messages GROUP BY session_id, seq)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_messages_session_seq "
                "ON chat_messages (session_id, seq)"
            ))
        except Exception:
            pass
    print("[1/4] 数据库表已创建 + 版本升级 DDL 已执行")

    async with SessionLocal() as db:
        # 超级管理员
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        exists = (
            await db.execute(select(AdminUser).where(AdminUser.username == admin_user))
        ).scalar_one_or_none()
        if not exists:
            db.add(AdminUser(
                username=admin_user, password_hash=hash_password(admin_pass),
                display_name="超级管理员", role=ROLE_SUPER_ADMIN,
            ))
            print(f"[2/4] 已创建超级管理员 {admin_user}（密码 {admin_pass}，请尽快修改）")
        else:
            # 把旧的默认 admin 升级为 super_admin（前向兼容）
            if exists.role != ROLE_SUPER_ADMIN:
                exists.role = ROLE_SUPER_ADMIN
                exists.display_name = "超级管理员"
            print("[2/4] 超级管理员已存在，跳过")

        # 其它种子角色（若不存在则创建）
        seed_accounts = [
            ("ops_admin",  ROLE_ADMIN,       "运营管理员"),
            ("leader",     ROLE_TEAM_LEADER, "客服主管 老张"),
            ("agent_li",   ROLE_AGENT,       "在线客服 小李"),
            ("agent_wang", ROLE_AGENT,       "在线客服 小王"),
            ("analyst",    ROLE_ANALYST,     "数据分析师 小陈"),
        ]
        for uname, role, display in seed_accounts:
            e = (await db.execute(select(AdminUser).where(AdminUser.username == uname))).scalar_one_or_none()
            if not e:
                db.add(AdminUser(
                    username=uname, password_hash=hash_password("Huami@2026"),
                    display_name=display, role=role,
                    presence="offline",
                ))
                print(f"      + 种子账号 {uname}（初始密码 Huami@2026）{display} [{role}]")
            else:
                # 前向兼容：补充角色、display_name
                e.role = role
                e.display_name = display

        await db.commit()
        print("[2/4] 种子账号就绪（共 6 角色）")

        # 商品
        if (await db.execute(select(func.count(Product.id)))).scalar() == 0:
            products = json.loads((SEEDS_DIR / "products.json").read_text("utf-8"))
            for p in products:
                db.add(Product(**p))
            print(f"[3/4] 已导入 {len(products)} 个种子商品")
        else:
            print("[3/4] 商品表非空，跳过商品导入")

        # 知识库
        if (await db.execute(select(func.count(KbDocument.id)))).scalar() == 0:
            kb = json.loads((SEEDS_DIR / "kb.json").read_text("utf-8"))
            count = 0
            for doc_type, docs in kb.items():
                for d in docs:
                    db.add(KbDocument(doc_type=doc_type, **d))
                    count += 1
            print(f"[3/4] 已导入 {count} 条知识库文档")
        else:
            print("[3/4] 知识库非空，跳过导入")

        # 示例订单
        if (await db.execute(select(func.count(Order.id)))).scalar() == 0:
            orders = json.loads((SEEDS_DIR / "orders.json").read_text("utf-8"))["orders"]
            for o in orders:
                db.add(Order(**o))
            await db.commit()
            print(f"[3/4] 已导入 {len(orders)} 个示例订单（可用于演示查订单）")
        else:
            print("[3/4] 订单表非空，跳过导入")

        # 系统设置默认值
        for key, value in DEFAULT_SETTINGS.items():
            exists_key = await db.get(Setting, key)
            if not exists_key:
                db.add(Setting(key=key, value=value))
        print("[3/4] 系统设置默认值已写入（人设/话术/兜底语/敏感词）")

        await db.commit()

    # ES 同步（可选）
    from app.services.embeddings import embedding_service
    from app.services.es_client import ESService
    from app.services.rag import RAGService

    es = ESService()
    rag = RAGService(es)
    try:
        await es.ensure_indices()
    except Exception as exc:
        print(f"[4/4] ES 未就绪（{exc}），跳过索引同步；启动服务后可在管理后台点「同步全部」")
        await es.client.close()
        return
    s = get_settings()
    if not embedding_service.enabled:
        print("[4/4] 未配置向量化服务（EMBEDDING_API_KEY），将以纯关键词模式同步")
    try:
        async with SessionLocal() as db:
            docs = (await db.execute(select(KbDocument))).scalars().all()
            total_chunks = 0
            for doc in docs:
                total_chunks += await rag.sync_kb_document(
                    {"id": doc.id, "doc_type": doc.doc_type, "title": doc.title,
                     "content": doc.content, "category": doc.category, "tags": doc.tags,
                     "enabled": doc.enabled}
                )
                doc.es_synced = True
            products = (await db.execute(select(Product))).scalars().all()
            for p in products:
                await rag.sync_product(
                    {"id": p.id, "name": p.name, "brand": p.brand, "category": p.category,
                     "price": float(p.price), "original_price": float(p.original_price) if p.original_price else None,
                     "stock": p.stock, "sales": p.sales, "rating": float(p.rating), "tags": p.tags,
                     "description": p.description, "selling_points": p.selling_points, "url": p.url,
                     "image_url": p.image_url, "enabled": p.enabled}
                )
                p.es_synced = True
            await db.commit()
        print(f"[4/4] ES 同步完成：知识库 {len(docs)} 篇 / {total_chunks} 块，商品 {len(products)} 个")
    finally:
        await es.client.close()


if __name__ == "__main__":
    asyncio.run(main())
