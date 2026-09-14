"""全局运行时对象（启动时初始化）"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent import AgentService
    from app.services.es_client import ESService
    from app.services.rag import RAGService


class AppState:
    es: "ESService | None" = None
    rag: "RAGService | None" = None
    agent: "AgentService | None" = None
    es_ready: bool = False


state = AppState()
