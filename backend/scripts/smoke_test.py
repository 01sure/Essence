"""接口冒烟测试：python scripts/smoke_test.py [base_url]"""
import asyncio
import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


async def main() -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        # 1. 健康检查
        r = await client.get(f"{BASE}/api/health")
        print("health:", r.status_code, r.json())
        assert r.status_code == 200

        # 2. 创建会话
        r = await client.post(
            f"{BASE}/api/chat/sessions",
            json={"visitor_id": "smoke-test", "page_url": "http://localhost/demo"},
        )
        print("create_session:", r.status_code)
        assert r.status_code == 200
        sid = r.json()["session_id"]

        # 3. SSE 流式对话（无 LLM Key 时应走兜底话术，验证全链路不崩）
        r = await client.post(
            f"{BASE}/api/chat/sessions/{sid}/stream",
            json={"content": "帮我查一下订单HU202608150001"},
        )
        print("stream status:", r.status_code)
        events = []
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        types = [e["type"] for e in events]
        print("stream events:", types)
        assert "done" in types, f"缺少 done 事件: {events}"
        deltas = "".join(e["content"] for e in events if e["type"] == "delta")
        print("assistant reply:", deltas[:120])

        # 4. 消息已持久化
        r = await client.get(f"{BASE}/api/chat/sessions/{sid}/messages")
        roles = [m["role"] for m in r.json()["messages"]]
        print("persisted messages:", roles)
        assert "user" in roles and "assistant" in roles

        # 5. 管理端：登录 + 看板 + 会话列表
        r = await client.post(
            f"{BASE}/api/admin/auth/login", json={"username": "admin", "password": "admin123"}
        )
        print("login:", r.status_code)
        assert r.status_code == 200
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(f"{BASE}/api/admin/dashboard", headers=headers)
        print("dashboard:", r.status_code, {k: r.json()[k] for k in ("today_sessions", "today_messages")})

        r = await client.get(f"{BASE}/api/admin/sessions", headers=headers)
        print("sessions:", r.status_code, "total =", r.json()["total"])

        r = await client.get(f"{BASE}/api/admin/products", headers=headers)
        print("products:", r.status_code, "total =", r.json()["total"])

        r = await client.get(f"{BASE}/api/admin/kb", headers=headers)
        print("kb:", r.status_code, "total =", r.json()["total"])

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
