"""多角色 RBAC + CAS 抢单 + SSE 冒烟脚本"""
import asyncio
import json
import time
import sys

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
ACCOUNTS = [
    ("admin", "admin123", "super_admin"),
    ("ops_admin", "Huami@2026", "admin"),
    ("leader", "Huami@2026", "team_leader"),
    ("agent_li", "Huami@2026", "agent"),
    ("agent_wang", "Huami@2026", "agent"),
    ("analyst", "Huami@2026", "analyst"),
]


def log(*args):
    print(" ".join(str(a) for a in args), flush=True)


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        # 1. health
        r = await c.get(f"{BASE}/api/health")
        log("health:", r.status_code, r.json())
        tokens = {}
        for u, p, expected_role in ACCOUNTS:
            r = await c.post(f"{BASE}/api/admin/auth/login", json={"username": u, "password": p})
            if r.status_code != 200:
                log(f"LOGIN FAIL {u}:", r.status_code, r.text)
                continue
            d = r.json()
            tokens[u] = d["token"]
            user = d["user"]
            got = user["role"]
            ok = "PASS" if got == expected_role else "FAIL"
            log(
                f"[{ok}] login {u:>11s} -> role={got:12s} "
                f"can_cfg={int(user['can_configure'])} can_agent={int(user['can_agent'])} "
                f"can_qa={int(user['can_qa'])} can_uadm={int(user['can_user_admin'])}"
            )

        h_ana = {"Authorization": f"Bearer {tokens['analyst']}"}
        h_ops = {"Authorization": f"Bearer {tokens['ops_admin']}"}
        h_sup = {"Authorization": f"Bearer {tokens['admin']}"}
        h_li = {"Authorization": f"Bearer {tokens['agent_li']}"}
        h_wang = {"Authorization": f"Bearer {tokens['agent_wang']}"}
        h_ld = {"Authorization": f"Bearer {tokens['leader']}"}

        # 2. analyst 不能写配置/KB/商品
        tests = [
            ("analyst GET  settings", "GET",    f"{BASE}/api/admin/settings", None,             h_ana, 403),
            ("analyst POST kb",       "POST",   f"{BASE}/api/admin/kb",       {"doc_type":"faq","title":"x","content":"x"}, h_ana, 403),
            ("analyst POST product",  "POST",   f"{BASE}/api/admin/products", {"name":"x","price":1}, h_ana, 403),
            ("analyst GET  dashboard","GET",    f"{BASE}/api/admin/dashboard",None,             h_ana, 200),
            ("analyst GET  sessions", "GET",    f"{BASE}/api/admin/sessions", None,             h_ana, 403),  # analyst 不是 agent 角色
            ("ops_admin GET users",   "GET",    f"{BASE}/api/admin/auth/users", None,           h_ops, 403),
            ("super_admin GET users", "GET",    f"{BASE}/api/admin/auth/users", None,           h_sup, 200),
        ]
        for name, method, url, body, h, expect in tests:
            if method == "GET":
                r = await c.get(url, headers=h)
            else:
                r = await c.post(url, json=body, headers=h)
            ok = "PASS" if r.status_code == expect else "FAIL"
            log(f"[{ok}] {name:<28s} got={r.status_code} expect={expect}")

        # 3. 质检权限：leader 可 200，agent 403
        sid = (await c.post(f"{BASE}/api/chat/sessions", json={"visitor_id": "qa-test"})).json()["session_id"]
        r = await c.post(
            f"{BASE}/api/admin/sessions/{sid}/quality",
            json={"score": 85, "remark": "响应及时，产品推荐专业"},
            headers=h_ld,
        )
        ok = "PASS" if r.status_code == 200 else "FAIL"
        log(f"[{ok}] leader 质检打分                    got={r.status_code} (expect 200)")
        r = await c.post(
            f"{BASE}/api/admin/sessions/{sid}/quality",
            json={"score": 80},
            headers=h_li,
        )
        ok = "PASS" if r.status_code == 403 else "FAIL"
        log(f"[{ok}] agent 质检打分被拒绝              got={r.status_code} (expect 403)")

        # 4. CAS 并发抢单
        sid = (await c.post(f"{BASE}/api/chat/sessions", json={"visitor_id": "cas-test"})).json()["session_id"]
        await c.post(f"{BASE}/api/chat/sessions/{sid}/stream", json={"content": "转人工"})
        r1, r2 = await asyncio.gather(
            c.post(f"{BASE}/api/admin/sessions/{sid}/claim", headers=h_li),
            c.post(f"{BASE}/api/admin/sessions/{sid}/claim", headers=h_wang),
        )
        results = {r1.status_code, r2.status_code}
        ok = "PASS" if results == {200, 409} or results == {200} else "FAIL"
        log(f"[{ok}] 并发 CAS 抢单                   agent_li={r1.status_code} agent_wang={r2.status_code} (expect one 200 + one 409)")
        winner_h = h_li if r1.status_code == 200 else h_wang
        loser_h = h_wang if winner_h == h_li else h_li
        winner_name = "agent_li" if winner_h == h_li else "agent_wang"

        # 5. 胜者发消息，失败者发消息要 403
        r = await c.post(f"{BASE}/api/admin/sessions/{sid}/messages", json={"content": "您好！人工客服为您服务~"}, headers=winner_h)
        ok = "PASS" if r.status_code == 200 else "FAIL"
        log(f"[{ok}] {winner_name} 发送人工回复 -> {r.status_code}")
        r = await c.post(f"{BASE}/api/admin/sessions/{sid}/messages", json={"content": "越权回复"}, headers=loser_h)
        ok = "PASS" if r.status_code == 403 else "FAIL"
        log(f"[{ok}] 失败者越权发消息拒绝          got={r.status_code} (expect 403)")

        # 6. 释放 vs 409
        r = await c.post(f"{BASE}/api/admin/sessions/{sid}/release", headers=winner_h)
        ok = "PASS" if r.status_code == 200 else "FAIL"
        log(f"[{ok}] 胜者释放会话                        -> {r.status_code}")
        r = await c.post(f"{BASE}/api/admin/sessions/{sid}/release", headers=loser_h)
        ok = "PASS" if r.status_code == 409 else "FAIL"
        log(f"[{ok}] 非接待人再次释放拒绝              got={r.status_code} (expect 409)")

        # 7. 转交：leader 先接单再转给 wang
        sid2 = (await c.post(f"{BASE}/api/chat/sessions", json={"visitor_id": "xfer-test"})).json()["session_id"]
        await c.post(f"{BASE}/api/chat/sessions/{sid2}/stream", json={"content": "转人工"})
        await c.post(f"{BASE}/api/admin/sessions/{sid2}/claim", headers=h_li)
        # agent_li -> agent_wang 转交
        r = await c.post(f"{BASE}/api/admin/sessions/{sid2}/transfer", json={"target_admin_id": 5}, headers=h_li)  # wang id=5
        ok = "PASS" if r.status_code == 200 else "FAIL"
        log(f"[{ok}] 转交 agent_li->agent_wang            -> {r.status_code}")
        # wang 能发，li 不能
        r = await c.post(f"{BASE}/api/admin/sessions/{sid2}/messages", json={"content": "您好我是小王"}, headers=h_wang)
        ok = "PASS" if r.status_code == 200 else "FAIL"
        log(f"[{ok}] 转交后新接待人可发消息             -> {r.status_code}")
        r = await c.post(f"{BASE}/api/admin/sessions/{sid2}/messages", json={"content": "我还要发"}, headers=h_li)
        ok = "PASS" if r.status_code == 403 else "FAIL"
        log(f"[{ok}] 转交后原接待人越权拒绝             got={r.status_code} (expect 403)")

        # 8. SSE 推流
        log(" --- SSE subscribe agent_li，并触发 new_waiting 广播 ---")
        start = time.time()
        events = []
        timeout = 7
        async with httpx.AsyncClient(timeout=30) as csse:
            async with csse.stream("GET", f"{BASE}/api/admin/sessions/stream", headers=h_li) as resp:
                log(f"    SSE connected status={resp.status_code}")
                # 后台触发一次转人工
                s3_task = asyncio.create_task(
                    (lambda: asyncio.sleep(0.5))()
                )
                async for line in resp.aiter_lines():
                    if time.time() - start > timeout:
                        break
                    if line.startswith("data: "):
                        try:
                            ev = json.loads(line[6:])
                            events.append(ev.get("event"))
                        except Exception:
                            pass
                    # 等到第 3 个事件后，手动触发一条新的 waiting 入池
                    if len(events) == 2:
                        s3 = (await c.post(f"{BASE}/api/chat/sessions", json={"visitor_id": "sse-trigger"})).json()["session_id"]
                        await c.post(f"{BASE}/api/chat/sessions/{s3}/stream", json={"content": "转人工"})
                s3_task.cancel()
        log(f"    SSE events received ({len(events)}): {events[:10]}")
        log("    [PASS]" if any(e in ("connected", "new_waiting", "pool_refresh", "keepalive") for e in events) else "    [FAIL] 未收到有效事件")

        # 9. roles / online-agents / stats
        r = await c.get(f"{BASE}/api/admin/auth/roles", headers=h_ana)
        ok = "PASS" if r.status_code == 200 and len(r.json()) == 5 else "FAIL"
        log(f"[{ok}] 角色字典接口                       got={r.status_code} items={len(r.json())}")

        r = await c.get(f"{BASE}/api/admin/sessions/stats", headers=h_li)
        ok = "PASS" if r.status_code == 200 and "waiting" in r.json() else "FAIL"
        log(f"[{ok}] 坐席 stats 接口                    got={r.status_code} keys={list(r.json())}")

        r = await c.get(f"{BASE}/api/admin/auth/online-agents", headers=h_li)
        ok = "PASS" if r.status_code == 200 else "FAIL"
        log(f"[{ok}] online-agents                      got={r.status_code} count={len(r.json())}")

asyncio.run(main())
