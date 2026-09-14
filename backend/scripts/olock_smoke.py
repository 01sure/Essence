"""商品/知识库/设置 乐观锁 409 用例 —— 后端 3 类运营并发编辑冲突验证"""
import asyncio
import sys
import httpx

BASE = "http://127.0.0.1:8000/api"

passed = 0
failed = 0


def check(name, cond, actual="", expect=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name:<36s} {actual}")
    else:
        failed += 1
        print(f"[FAIL] {name:<36s} actual={actual} expect={expect}")


async def login(c, username, password=None):
    if password is None:
        password = "admin123" if username == "admin" else "Huami@2026"
    r = await c.post(f"{BASE}/admin/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login fail {username}: {r.status_code} {r.text}"
    return r.json()["token"]


async def get_setting_token(c, H):
    items = (await c.get(f"{BASE}/admin/settings", headers=H)).json()["items"]
    person = next(x for x in items if x["key"] == "persona")
    return person.get("updated_at"), person.get("value")


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        tok_ops = await login(c, "ops_admin")
        H = {"Authorization": f"Bearer {tok_ops}"}

        # ------------- (product) --------------
        p = (await c.post(f"{BASE}/admin/products", json={"name": "olock-p1", "price": 1299, "stock": 10}, headers=H)).json()
        pid = p["id"]
        # 确保取到 updated_at（先等待 SQL 毫秒推进）
        await asyncio.sleep(0.02)
        lst = (await c.get(f"{BASE}/admin/products", headers=H)).json()["items"]
        row = next(x for x in lst if x["id"] == pid)
        uat = row.get("updated_at")
        check("(product) list 有 updated_at", bool(uat), f"{uat[:19]}" if uat else "None", "非空")
        # 先做一次"空写入"保证 updated_at 一定晚于 uat，避免刚创建和首更新撞同一秒
        await asyncio.sleep(1.1)

        r = await c.put(f"{BASE}/admin/products/{pid}", json={
            "name": "olock-p1-c1", "price": 1299, "stock": 10, "brand": "Amazfit",
            "category": "智能手表", "rating": 4.8, "enabled": True,
            "if_match_updated_at": uat,
        }, headers=H)
        check("(product) 首次更新", r.status_code == 200, f"{r.status_code}", "200")
        new_uat = r.json().get("updated_at") if r.status_code == 200 else None

        r = await c.put(f"{BASE}/admin/products/{pid}", json={
            "name": "olock-p1-c2", "price": 1299, "stock": 10, "brand": "Amazfit",
            "category": "智能手表", "rating": 4.8, "enabled": True,
            "if_match_updated_at": uat,
        }, headers=H)
        check("(product) 旧 token 冲突 => 409", r.status_code == 409, f"{r.status_code}", "409")

        if new_uat:
            r = await c.put(f"{BASE}/admin/products/{pid}", json={
                "name": "olock-p1-c3", "price": 1299, "stock": 10, "brand": "Amazfit",
                "category": "智能手表", "rating": 4.8, "enabled": True,
                "if_match_updated_at": new_uat,
            }, headers=H)
            check("(product) 新 token 再更新 => 200", r.status_code == 200, f"{r.status_code}", "200")
        await c.delete(f"{BASE}/admin/products/{pid}", headers=H)

        # ------------- (settings) --------------
        s_old, _ = await get_setting_token(c, H)
        check("(settings) GET 带 updated_at", bool(s_old), f"{s_old[:19] if s_old else None}", "非空")
        await asyncio.sleep(1.1)  # 等 1s+ 让新 updated_at 必定 > 原值

        r = await c.put(f"{BASE}/admin/settings/persona", json={"value": "人设V1", "if_match_updated_at": s_old}, headers=H)
        check("(settings) 首次保存", r.status_code == 200, f"{r.status_code}", "200")
        s_new = r.json().get("updated_at") if r.status_code == 200 else None

        r = await c.put(f"{BASE}/admin/settings/persona", json={"value": "人设V2", "if_match_updated_at": s_old}, headers=H)
        check("(settings) 旧 token 冲突 => 409", r.status_code == 409, f"{r.status_code}", "409")

        # ------------- (kb) --------------
        kb = (await c.post(f"{BASE}/admin/kb", json={"doc_type": "faq", "title": "olock-k1", "content": "c0", "category": "通用"}, headers=H)).json()
        kid = kb["id"]
        await asyncio.sleep(1.1)
        lst = (await c.get(f"{BASE}/admin/kb", headers=H)).json()["items"]
        krow = next(x for x in lst if x["id"] == kid)
        kuat = krow.get("updated_at")
        check("(kb) list 有 updated_at", bool(kuat), f"{kuat[:19]}" if kuat else None, "非空")

        r = await c.put(f"{BASE}/admin/kb/{kid}", json={
            "doc_type": "faq", "title": "olock-k1-c1", "content": "c1", "category": "通用", "enabled": True,
            "if_match_updated_at": kuat,
        }, headers=H)
        check("(kb) 首次保存", r.status_code == 200, f"{r.status_code}", "200")
        new_kuat = r.json().get("updated_at") if r.status_code == 200 else None

        r = await c.put(f"{BASE}/admin/kb/{kid}", json={
            "doc_type": "faq", "title": "olock-k1-c2", "content": "c2", "category": "通用", "enabled": True,
            "if_match_updated_at": kuat,
        }, headers=H)
        check("(kb) 旧 token 冲突 => 409", r.status_code == 409, f"{r.status_code}", "409")

        # 并发写入 product：两边都拿 uat，先写的 200 后写的 409
        tok_a = await login(c, "ops_admin")
        tok_b = await login(c, "admin")
        Ha = {"Authorization": f"Bearer {tok_a}"}
        Hb = {"Authorization": f"Bearer {tok_b}"}
        p2 = (await c.post(f"{BASE}/admin/products", json={"name": "olock-p-concurrent", "price": 1999, "stock": 5}, headers=Ha)).json()
        pid2 = p2["id"]
        await asyncio.sleep(1.1)
        lst = (await c.get(f"{BASE}/admin/products", headers=Ha)).json()["items"]
        uat2 = next(x for x in lst if x["id"] == pid2).get("updated_at")
        common = {
            "price": 1999, "stock": 5, "brand": "Amazfit", "category": "智能手表",
            "rating": 4.8, "enabled": True, "if_match_updated_at": uat2,
        }
        ra, rb = await asyncio.gather(
            c.put(f"{BASE}/admin/products/{pid2}", json={**common, "name": "并发-A"}, headers=Ha),
            c.put(f"{BASE}/admin/products/{pid2}", json={**common, "name": "并发-B"}, headers=Hb),
            return_exceptions=False,
        )
        codes = sorted([ra.status_code, rb.status_code])
        ok_cas = codes == [200, 409]
        check("(product) 并发写入 => 一胜200一负409", ok_cas, f"{codes}", "[200, 409]")
        await c.delete(f"{BASE}/admin/products/{pid2}", headers=Ha)
        await c.delete(f"{BASE}/admin/kb/{kid}", headers=H)

    print(f"\n乐观锁冒烟：passed={passed} failed={failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
