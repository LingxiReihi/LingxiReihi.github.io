import io
import zipfile

import pytest
from PIL import Image

from tests.test_public import seed_contents  # noqa: F401 复用


async def _png_bytes(color=(255, 0, 0)):
    im = Image.new("RGB", (800, 450), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


async def test_contents_require_auth(client):
    r = await client.get("/api/v1/admin/contents")
    assert r.status_code == 401


async def test_create_publish_chain(auth, client):
    r = await auth.post("/api/v1/admin/contents", json={
        "type": "article", "status": "draft", "title": "我的第一篇",
        "summary": "hi", "body_md": "# hello", "tags": [{"name": "技术"}]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    slug, cid = d["slug"], d["id"]
    assert d["status"] == "draft"
    # draft 不对外
    assert (await client.get(f"/api/v1/posts/{slug}")).status_code == 404
    # preview token
    r = await auth.post(f"/api/v1/admin/contents/{cid}/preview-token")
    token = r.json()["data"]["token"]
    r = await client.get(f"/api/v1/posts/{slug}/preview?token={token}")
    assert r.status_code == 200 and r.json()["data"]["body_md"] == "# hello"
    # 发布
    r = await auth.patch(f"/api/v1/admin/contents/{cid}/status", json={"status": "published"})
    assert r.json()["data"]["pipeline"]["queued"] is True
    r = await client.get(f"/api/v1/posts/{slug}")
    assert r.status_code == 200
    # sitemap 已含新 URL
    r = await client.get("/sitemap.xml")
    assert f"/blog/{slug}" in r.text
    # 列表可见
    r = await auth.get("/api/v1/admin/contents?type=article&status=published")
    assert r.json()["data"]["total"] >= 1


async def test_publish_via_put_full_payload(auth, client):
    """编辑器「确定发布」走 PUT 全量提交：slug 在 body 中，draft→published 不得 500。"""
    r = await auth.post("/api/v1/admin/contents", json={
        "type": "article", "status": "draft", "title": "PUT发布", "body_md": "正文"})
    d = r.json()["data"]
    cid, slug = d["id"], d["slug"]
    r = await auth.put(f"/api/v1/admin/contents/{cid}", json={
        "type": "article", "status": "published", "title": "PUT发布", "slug": slug,
        "summary": "s", "body_md": "正文", "tags": [], "asset_ids": [], "extra": {}})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "published"
    assert (await client.get(f"/api/v1/posts/{slug}")).status_code == 200
    # 已发布后 slug 不可变
    r = await auth.put(f"/api/v1/admin/contents/{cid}", json={
        "type": "article", "status": "published", "title": "PUT发布", "slug": "hacked-slug"})
    assert r.status_code == 200 and r.json()["data"]["slug"] == slug


async def test_publish_put_generates_slug_when_empty(auth, client):
    """草稿期留空 slug、发布弹窗不填直接确定：发布时按标题自动生成，不得产生空 slug 公开页。"""
    r = await auth.post("/api/v1/admin/contents", json={
        "type": "article", "status": "draft", "title": "自动生成 slug", "body_md": "b"})
    d = r.json()["data"]
    cid = d["id"]
    await auth.put(f"/api/v1/admin/contents/{cid}", json={"slug": ""})
    r = await auth.put(f"/api/v1/admin/contents/{cid}", json={
        "status": "published", "title": "自动生成 slug"})
    assert r.status_code == 200, r.text
    new_slug = r.json()["data"]["slug"]
    assert new_slug
    assert (await client.get(f"/api/v1/posts/{new_slug}")).status_code == 200


async def test_slug_conflict(auth):
    r = await auth.post("/api/v1/admin/contents",
                        json={"type": "article", "title": "A", "slug": "dup-slug"})
    assert r.status_code == 200
    r = await auth.post("/api/v1/admin/contents",
                        json={"type": "article", "title": "B", "slug": "dup-slug"})
    assert r.status_code == 409 and r.json()["data"]["field"] == "slug"


async def test_media_upload_dedup_and_delete(auth):
    data = await _png_bytes()
    files = {"file": ("red.png", io.BytesIO(data), "image/png")}
    r = await auth.post("/api/v1/admin/media", files=files)
    assert r.status_code == 200, r.text
    a1 = r.json()["data"]
    assert a1["width"] == 800 and a1["thumb"].endswith(".webp")
    # sha256 秒传
    r = await auth.post("/api/v1/admin/media", files={"file": ("red-clone.png", io.BytesIO(data), "image/png")})
    assert r.json()["data"]["id"] == a1["id"]
    # 被引用禁删
    r = await auth.post("/api/v1/admin/contents",
                        json={"type": "article", "title": "cover test", "slug": "cover-test",
                              "cover_asset_id": a1["id"]})
    cid = r.json()["data"]["id"]
    r = await auth.delete(f"/api/v1/admin/media/{a1['id']}")
    assert r.status_code == 409 and cid in r.json()["data"]["content_ids"]
    await auth.delete(f"/api/v1/admin/contents/{cid}")
    r = await auth.delete(f"/api/v1/admin/media/{a1['id']}")
    assert r.status_code == 200


async def test_media_type_whitelist(auth):
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("evil.exe", io.BytesIO(b"MZ...."), "application/x-msdownload")})
    assert r.status_code == 415


async def test_media_model3d_only_glb_and_zip(auth):
    """3D 只收 glb（预览）与 zip（工程包）；散格式与文件夹成员一律引导打包。"""
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("cube.glb", b"glTF\x02\x00\x00\x00" + b"\0" * 40, "model/gltf-binary")})
    assert r.status_code == 200 and r.json()["data"]["kind"] == "model3d"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("scene/scene.obj", "v 0 0 0\n")
        zf.writestr("scene/scene.mtl", "newmtl x\n")
        zf.writestr("scene/tex/wood.png", b"pngbytes")
        zf.writestr("scene/", b"")           # 目录项不进清单
        zf.writestr("../escape.txt", b"x")   # 越界路径丢弃
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("scene.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    entries = r.json()["data"]["entries"]
    assert [e["path"] for e in entries] == ["scene/scene.obj", "scene/scene.mtl", "scene/tex/wood.png"]
    assert entries[2]["size"] == 8

    for name in ["a.obj", "a.mtl", "a.fbx", "a.blend", "a.max", "a.tga"]:
        r = await auth.post("/api/v1/admin/media",
                            files={"file": (name, io.BytesIO(b"x" * 64), "application/octet-stream")})
        assert r.status_code == 415, name
        assert "zip" in r.json()["message"], name


async def test_media_category_upload_and_filter(auth):
    data = await _png_bytes((0, 200, 0))
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("av.png", io.BytesIO(data), "image/png")},
                        data={"category": "avatar"})
    assert r.status_code == 200, r.text
    a = r.json()["data"]
    assert a["category"] == "avatar" and a["storage_key"].startswith("avatar/")
    from pathlib import Path
    from app.core.config import settings
    assert (settings.media_path / a["storage_key"]).exists()
    assert (settings.media_path / a["thumb"].removeprefix("/media/")).exists()
    # 默认 blog
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("blog.png", io.BytesIO(await _png_bytes((0, 0, 200))), "image/png")})
    assert r.json()["data"]["storage_key"].startswith("blog/")
    # 站点素材：首页圆图与 favicon 都归这一类（SettingsView 的 MediaPicker 传 category="site"）
    site_bytes = await _png_bytes((10, 20, 30))
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("icon.png", io.BytesIO(site_bytes), "image/png")},
                        data={"category": "site"})
    assert r.status_code == 200, r.text
    s = r.json()["data"]
    assert s["category"] == "site" and s["storage_key"].startswith("site/")
    # 非法分类
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("x.png", io.BytesIO(data), "image/png")},
                        data={"category": "wallet"})
    assert r.status_code == 400
    # 筛选
    r = await auth.get("/api/v1/admin/media?category=avatar")
    assert [x["id"] for x in r.json()["data"]["items"]] == [a["id"]]


async def test_media_recategorize_keeps_file_and_url(auth):
    """改分类只动标签：文件不搬、URL 不变（细节见 tests/test_media_manage.py）。"""
    data = await _png_bytes((200, 0, 200))
    r = await auth.post("/api/v1/admin/media",
                        files={"file": ("m.png", io.BytesIO(data), "image/png")},
                        data={"category": "blog"})
    a = r.json()["data"]
    r = await auth.post("/api/v1/admin/media/categorize",
                        json={"ids": [a["id"]], "category": "model"})
    assert r.status_code == 200 and r.json()["data"]["updated"] == 1
    r = await auth.get("/api/v1/admin/media?category=model")
    m = [x for x in r.json()["data"]["items"] if x["id"] == a["id"]][0]
    assert m["storage_key"] == a["storage_key"] and m["url"] == a["url"]
    # 非法目标分类
    r = await auth.post("/api/v1/admin/media/categorize", json={"ids": [a["id"]], "category": "x"})
    assert r.status_code == 400


async def test_settings_group_roundtrip(auth, client):
    r = await auth.put("/api/v1/admin/settings/site",
                       json={"title": "New Title", "subtitle": "sub"})
    assert r.json()["data"]["site"]["title"] == "New Title"
    r = await client.get("/api/v1/site-config")
    assert r.json()["data"]["site"]["title"] == "New Title"


async def test_tags_crud(auth):
    r = await auth.post("/api/v1/admin/tags", json={"name": "新标签"})
    tid = r.json()["data"]["id"]
    r = await auth.put(f"/api/v1/admin/tags/{tid}", json={"name": "改名了"})
    assert r.json()["data"]["name"] == "改名了"
    r = await auth.delete(f"/api/v1/admin/tags/{tid}")
    assert r.status_code == 200


async def test_stats_endpoints(auth, client):
    from app.core.db import SessionLocal
    from app.models import ViewEvent
    from datetime import datetime, timezone
    day = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
    async with SessionLocal() as db:
        db.add_all([
            ViewEvent(day=day, path="/api/v1/posts/x", content_id=None, referrer="https://www.baidu.com/s",
                      ip_hash="a" * 32, ua_hash="b" * 32, status_code=200),
            ViewEvent(day=day, path="/api/v1/home", content_id=None, referrer="",
                      ip_hash="c" * 32, ua_hash="d" * 32, status_code=200),
        ])
        await db.commit()
    from app.services.settings import get_group  # noqa  # 确认导入不报错
    # 聚合
    from app.tasks.aggregate import run_aggregate, _today
    async with SessionLocal() as db:
        await run_aggregate(db, _today())
    r = await auth.get("/api/v1/admin/stats/overview")
    assert r.json()["data"]["today"]["pv"] == 2
    r = await auth.get("/api/v1/admin/stats/trend")
    assert r.json()["data"]["days"][-1]["pv"] == 2
    r = await auth.get("/api/v1/admin/stats/sources")
    assert r.json()["data"]["search"] == 1 and r.json()["data"]["direct"] == 1
    r = await auth.get("/api/v1/admin/stats/export")
    assert "daily" in r.text


async def test_seo_panel(auth):
    r = await auth.get("/api/v1/admin/seo/config")
    d = r.json()["data"]
    assert d["api_configured"] is False and d["rebuild_configured"] is False
    # 无 token 时手动推送 => 入待推队列
    r = await auth.post("/api/v1/admin/seo/push", json={"urls": ["https://example.com/blog/p1"]})
    assert r.json()["data"]["skipped"] == 1
    # 再推 pending
    r = await auth.post("/api/v1/admin/seo/push", json={"pending": True})
    assert r.json()["data"]["skipped"] == 1
    r = await auth.get("/api/v1/admin/seo/push-logs")
    assert len(r.json()["data"]["items"]) >= 2


async def test_robots_txt(client):
    r = await client.get("/robots.txt")
    assert r.status_code == 200 and "Disallow: /admin" in r.text and "Sitemap" in r.text


async def test_rebuild_watcher_request_file(auth, tmp_path):
    """Docker 模式：未配 REBUILD_SCRIPT 但配了 REBUILD_REQUEST_FILE => 写请求文件、job=requested。"""
    import asyncio
    from pathlib import Path
    from app.core.config import settings
    from app.services import rebuild
    req = tmp_path / ".rebuild-request"
    orig_script, orig_req = settings.rebuild_script, settings.rebuild_request_file
    settings.rebuild_script, settings.rebuild_request_file = "", str(req)
    try:
        r = await auth.post("/api/v1/admin/contents", json={
            "type": "article", "status": "draft", "title": "watcher", "body_md": "x"})
        cid = r.json()["data"]["id"]
        await auth.patch(f"/api/v1/admin/contents/{cid}/status", json={"status": "published"})
        await asyncio.sleep(0.3)   # 等合并窗口(0s)后的后台任务落文件
        assert req.exists()
        assert "/blog/" in req.read_text(encoding="utf-8")
        jobs = (await auth.get("/api/v1/admin/seo/jobs")).json()["data"]["items"]
        assert jobs and jobs[0]["status"] == "requested"
    finally:
        settings.rebuild_script, settings.rebuild_request_file = orig_script, orig_req
