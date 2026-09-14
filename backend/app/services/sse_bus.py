"""
简易进程内事件总线：
  - 坐席端 SSE 订阅 /admin/sessions/stream
  - 新会话进入 waiting_human 池时广播 new_waiting
  - 人工写入消息、或访客新消息时广播给对应会话的接待人
  - 领取/释放/转交/关闭时广播 pool_refresh 给全部客服
单进程内实现，多实例部署时可替换为 Redis pub/sub（接口不变）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import BackgroundTasks, Request

logger = logging.getLogger(__name__)

# admin_id -> asyncio.Queue ；None key 是"全局广播"（只发 pool_refresh/new_waiting）
_subscribers: dict[int | None, set[asyncio.Queue]] = {}
_lock = asyncio.Lock()


async def subscribe(admin_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    async with _lock:
        _subscribers.setdefault(admin_id, set()).add(q)
        _subscribers.setdefault(None, set()).add(q)  # 每个订阅者也收全局广播
    logger.debug("sessions stream subscribed admin=%s", admin_id)
    return q


async def unsubscribe(admin_id: int, q: asyncio.Queue) -> None:
    async with _lock:
        for key in (admin_id, None):
            bucket = _subscribers.get(key)
            if bucket:
                bucket.discard(q)
                if not bucket:
                    _subscribers.pop(key, None)


async def _push(q: asyncio.Queue, payload: dict[str, Any]) -> None:
    try:
        if q.full():
            q.get_nowait()
        q.put_nowait(payload)
    except Exception:  # noqa: BLE001
        pass


async def broadcast(admin_ids: list[int] | None, event: dict[str, Any]) -> None:
    """admin_ids=None 时走全局广播通道"""
    async with _lock:
        if admin_ids is None:
            receivers: set[asyncio.Queue] = set(_subscribers.get(None, set()))
        else:
            receivers: set[asyncio.Queue] = set()
            for aid in admin_ids:
                receivers |= _subscribers.get(aid, set())
    for q in receivers:
        await _push(q, event)


# -------- 便捷封装：会话生命周期钩子 --------

async def on_new_waiting(session_id: str, visitor_id: str) -> None:
    await broadcast(None, {"event": "new_waiting", "session_id": session_id, "visitor_id": visitor_id})


async def on_pool_changed() -> None:
    await broadcast(None, {"event": "pool_refresh"})


async def on_session_message(session_id: str, human_admin_id: int | None, payload: dict) -> None:
    """人工接待的会话，有任何新消息推给对应坐席"""
    if human_admin_id is None:
        return
    ev = {"event": "new_message", "session_id": session_id}
    ev.update(payload)
    await broadcast([human_admin_id], ev)
