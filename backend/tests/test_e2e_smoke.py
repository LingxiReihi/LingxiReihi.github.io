"""端到端冒烟（docs 计划 M7）：
seed 管理员 → 登录 → 传图 → 建草稿 → 发布（rebuild skipped）→ 公开读取 →
PV 采集 → 日聚合 → 看板出数 → sitemap/robots 校验。"""
import io
from datetime import datetime, timezone

from PIL import Image
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import PendingPush, RebuildJob, SiteSetting, StatsDaily, ViewEvent
from app.tasks.aggregate import run_aggregate


async def _login(client):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


async def test_e2e_smoke(client, admin_user):
    # 1. 登录
    token = await _login(client)
    H = {"Authorization": f"Bearer {token}"}

    # 2. 上传封面（1x1 png）+ sha256 秒传验证
    im = Image.new("RGB", (64, 36), (57, 197, 187))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    png = buf.getvalue()
    r = await client.post("/api/v1/admin/media", files={"file": ("e2e.png", io.BytesIO(png), "image/png")}, headers=H)
    assert r.status_code == 200, r.text
    asset = r.json()["data"]
    r2 = await client.post("/api/v1/admin/media", files={"file": ("e2e-copy.png", io.BytesIO(png), "image/png")}, headers=H)
    assert r2.json()["data"]["id"] == asset["id"]  # 秒传

    # 3. 建草稿
    r = await client.post("/api/v1/admin/contents", headers=H, json={
        "type": "article", "status": "draft", "title": "E2E 冒烟文章", "slug": "e2e-smoke",
        "summary": "端到端", "body_md": "# E2E\n\n正文内容", "cover_asset_id": asset["id"],
        "tags": [{"name": "E2E"}],
    })
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["id"]

    # 草稿不对外
    assert (await client.get("/api/v1/posts/e2e-smoke")).status_code == 404

    # 4. 发布（REBUILD_SCRIPT 未配置 → skipped + pending_push 链路）
    r = await client.patch(f"/api/v1/admin/contents/{cid}/status", json={"status": "published"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["pipeline"]["queued"] is True

    # 5. 公开读取 + 首页聚合 + RSS
    r = await client.get("/api/v1/posts/e2e-smoke")
    assert r.status_code == 200
    assert r.json()["data"]["cover"] == asset["url"]
    r = await client.get("/api/v1/home")
    assert any(p["slug"] == "e2e-smoke" for p in r.json()["data"]["recent_posts"])
    r = await client.get("/api/v1/rss")
    assert "E2E 冒烟文章" in r.text

    # 6. PV 采集（track_local=1 强制）
    await client.get("/api/v1/posts/e2e-smoke?track_local=1")
    await client.get("/api/v1/posts/e2e-smoke?track_local=1")
    async with SessionLocal() as db:
        n = (await db.execute(select(func.count()).select_from(ViewEvent))).scalar_one()
        assert n >= 2
        # 7. 聚合
        day = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
        await run_aggregate(db, day)
        sd = (await db.execute(select(StatsDaily).where(StatsDaily.day == day))).scalar_one()
        assert sd.pv >= 2

    # 8. 看板端点出数
    r = await client.get("/api/v1/admin/stats/overview", headers=H)
    assert r.json()["data"]["today"]["pv"] >= 2
    r = await client.get("/api/v1/admin/stats/top-content", headers=H)
    assert any(x["content_id"] == cid for x in r.json()["data"]["items"])

    # 9. SEO：sitemap 含新 URL、robots 屏蔽 admin、pending_push、rebuild job skipped
    r = await client.get("/sitemap.xml")
    assert "/blog/e2e-smoke" in r.text
    r = await client.get("/robots.txt")
    assert "Disallow: /admin" in r.text
    async with SessionLocal() as db:
        pp = (await db.execute(select(PendingPush).where(PendingPush.url.endswith("/blog/e2e-smoke")))).scalars().first()
        assert pp is not None  # token 未配置 → 待推队列
        job = (await db.execute(select(RebuildJob).order_by(RebuildJob.id.desc()))).scalars().first()
        assert job is not None and job.status == "skipped"

    # 10. 批量补推（仍无 token → 保持 pending 语义，返回 skipped 计数）
    r = await client.post("/api/v1/admin/seo/push", json={"pending": True}, headers=H)
    assert r.status_code == 200

    # 11. 下架 → 公开 404 → sitemap 移除
    r = await client.patch(f"/api/v1/admin/contents/{cid}/status", json={"status": "archived"}, headers=H)
    assert r.status_code == 200
    assert (await client.get("/api/v1/posts/e2e-smoke")).status_code == 404
    r = await client.get("/sitemap.xml")
    assert "/blog/e2e-smoke" not in r.text

    # 12. 删除内容
    r = await client.delete(f"/api/v1/admin/contents/{cid}", headers=H)
    assert r.status_code == 200


async def test_settings_drive_frontend_api(client, admin_user):
    """站点设置 → 公开 API 联动（Flow G 冒烟）。"""
    token = await _login(client)
    H = {"Authorization": f"Bearer {token}"}
    # 资料跟人走：改自己的资料走 /admin/profile（super 的那份即站点 About）
    r = await client.put("/api/v1/admin/profile", headers=H, json={
        "nickname": "E2E昵称", "signature": "sig", "bio_md": "", "avatar": "",
        "social_links": [{"platform": "GitHub", "url": "https://github.com/x"}],
        "skills": [], "experience": [],
    })
    assert r.status_code == 200
    r = await client.get("/api/v1/about")
    assert r.json()["data"]["nickname"] == "E2E昵称"
    r = await client.get("/api/v1/home")
    assert r.json()["data"]["profile"]["nickname"] == "E2E昵称"
    async with SessionLocal() as db:
        from app.models import User
        u = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
        assert u.nickname == "E2E昵称" and u.social_links[0]["platform"] == "GitHub"
