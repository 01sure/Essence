"""统一日志配置"""
import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    root.addHandler(handler)
    # 降低三方库噪音
    for name in ("httpx", "openai", "elasticsearch", "aiomysql", "aiosqlite", "urllib3", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)
