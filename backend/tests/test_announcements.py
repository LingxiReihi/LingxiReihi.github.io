"""更新公告：表结构 / API 契约 / 权限 / 排序。"""
import pytest
from sqlalchemy import text as sa_text

from app.core.db import SessionLocal


@pytest.mark.asyncio
async def test_table_created_from_metadata():
    from sqlalchemy import inspect

    from app.models import Announcement  # noqa: F401  (Task 1 先建模型)
    from app.core.db import engine
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda s: inspect(s).get_columns("announcements"))}
    assert cols == {"id", "title", "body_md", "status", "published_at",
                    "created_at", "updated_at", "created_by_id"}


@pytest.mark.asyncio
async def test_reads_table_shape():
    from sqlalchemy import inspect

    from app.core.db import engine
    from app.models import AnnouncementRead  # noqa: F401
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda s: inspect(s).get_columns("announcement_reads"))}
        fks = await conn.run_sync(lambda s: {
            (f["constrained_columns"][0], f["options"].get("ondelete"))
            for f in inspect(s).get_foreign_keys("announcement_reads")})
    assert cols == {"announcement_id", "user_id", "read_at"}
    assert fks == {("announcement_id", "CASCADE"), ("user_id", "CASCADE")}


async def _post(auth, **over):
    body = {"title": "v1 上线", "body_md": "## 变更\n- 表格 | a | b |\n|---|---|\n| 1 | 2 |",
            "status": "published", "published_at": "2026-10-14T12:00:00+00:00"}
    body.update(over)
    return await auth.post("/api/v1/admin/announcements", json=body)


async def _staff_client(auth, make_staff, username, grants):
    await make_staff(username, grants=grants)
    from httpx import ASGITransport, AsyncClient
    from app.main import app as fastapi_app
    c = AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test")
    r = await c.post("/api/v1/admin/auth/login",
                     json={"username": username, "password": "staff-pass-123"})
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


@pytest.mark.asyncio
async def test_crud_flow(auth):
    r = await _post(auth)
    assert r.status_code == 200 and r.json()["code"] == 0
    a = r.json()["data"]
    assert a["status"] == "published" and a["created_by"] == "Test"
    got = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert got[0]["id"] == a["id"]
    r2 = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"title": "v1 修订"})
    assert r2.status_code == 200 and r2.json()["data"]["title"] == "v1 修订"
    assert r2.json()["data"]["body_md"] == a["body_md"]          # 部分更新不动其它字段
    assert (await auth.delete(f"/api/v1/admin/announcements/{a['id']}")).status_code == 200
    assert (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_staff_without_perm_gets_403_on_read_and_write(auth, make_staff):
    c = await _staff_client(auth, make_staff, "s_noperm", [])
    r = await c.get("/api/v1/admin/announcements")
    assert r.status_code == 403 and r.json()["code"] == 40300
    assert "更新公告" in r.json()["message"]
    assert (await c.post("/api/v1/admin/announcements", json={"title": "x"})).status_code == 403
    await c.aclose()


@pytest.mark.asyncio
async def test_staff_with_announcement_perm(auth, make_staff):
    c = await _staff_client(auth, make_staff, "s_ann",
                            [{"permission": "announcement:manage"}])
    assert (await c.get("/api/v1/admin/announcements")).status_code == 200
    assert (await _post(c, title="授权可写")).status_code == 200
    await c.aclose()


@pytest.mark.asyncio
async def test_title_blank_rejected(auth):
    # 实测口径：RequestValidationError 全局 handler 统一转 422——空串走 min_length、
    # 纯空白走 field_validator(ValueError)，同为 422（brief 预告的裁决点，以实测为准）。
    assert (await _post(auth, title="")).status_code == 422
    assert (await _post(auth, title="   ")).status_code == 422


@pytest.mark.asyncio
async def test_unknown_status_422(auth):
    assert (await _post(auth, status="archived")).status_code == 422


@pytest.mark.asyncio
async def test_ordering_published_desc_then_draft(auth):
    await _post(auth, title="早", published_at="2026-09-01T00:00:00+00:00")
    await _post(auth, title="晚", published_at="2026-10-01T00:00:00+00:00")
    await _post(auth, title="草稿", status="draft", published_at=None)
    items = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert [i["title"] for i in items] == ["晚", "早", "草稿"]


@pytest.mark.asyncio
async def test_draft_without_date_and_republish_keeps_first_date(auth):
    a = (await _post(auth, status="draft", published_at=None)).json()["data"]
    assert a["published_at"] is None and a["status"] == "draft"
    r = await auth.put(f"/api/v1/admin/announcements/{a['id']}",
                       json={"status": "published", "published_at": None})
    assert r.json()["data"]["published_at"] is not None          # 置发布且没给日期 → 补 now
    first = r.json()["data"]["published_at"]
    r2 = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"status": "draft"})
    assert r2.json()["data"]["published_at"] == first             # 改回草稿不清空
    r3 = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"status": "published"})
    assert r3.json()["data"]["published_at"] == first             # 重发布不覆盖首发时间


@pytest.mark.asyncio
async def test_unpublished_draft_with_date_still_bottom(auth):
    # spec §2「draft 恒排在其后」：先发布后改回草稿的条目保留旧 published_at（apply_write 第三条），
    # 必须按 status 分组垫底，不能带着时间戳混进 published 组中间。
    await _post(auth, title="A", published_at="2026-10-10T00:00:00+00:00")
    await _post(auth, title="B", published_at="2026-10-01T00:00:00+00:00")
    d = (await _post(auth, title="改回草稿", published_at="2026-10-05T00:00:00+00:00")).json()["data"]
    r = await auth.put(f"/api/v1/admin/announcements/{d['id']}", json={"status": "draft"})
    assert r.json()["data"]["published_at"] is not None      # 前提成立：该草稿带旧时间戳
    items = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert [i["title"] for i in items] == ["A", "B", "改回草稿"]


@pytest.mark.asyncio
async def test_created_by_set_null_on_user_delete(auth, make_staff):
    # 实测裁决：原用例删除的是登录者本人（admin），删后其 token 在 get_current_admin
    # 即 401「登录已失效」，到不了公告路由——非实现缺陷。改为删「公告的作者(staff)」、
    # 由幸存的 admin 读，保留原 API 层 SET NULL 断言不变。
    c = await _staff_client(auth, make_staff, "s_author",
                            [{"permission": "announcement:manage"}])
    a = (await _post(c)).json()["data"]
    assert a["created_by"] == "s_author"
    await c.aclose()
    async with SessionLocal() as db:
        from sqlalchemy import delete

        from app.models import User
        await db.execute(delete(User).where(User.username == "s_author"))
        await db.commit()
    items = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert items[0]["id"] == a["id"] and items[0]["created_by"] is None


@pytest.mark.asyncio
async def test_put_missing_id_404(auth):
    assert (await auth.put("/api/v1/admin/announcements/99999", json={"title": "x"})).status_code == 404
    assert (await auth.delete("/api/v1/admin/announcements/99999")).status_code == 404


async def _uid(username: str) -> int:
    async with SessionLocal() as db:
        return (await db.execute(sa_text("select id from users where username = :u"),
                                 {"u": username})).scalar_one()


@pytest.mark.asyncio
async def test_unread_readable_without_manage_perm(auth, make_staff):
    await _post(auth, title="全员可见")
    # 草稿是作者自己没写完的备忘，不该弹给其他人 → /unread 只推 published。
    await _post(auth, title="作者草稿", status="draft", published_at=None)
    c = await _staff_client(auth, make_staff, "s_readonly", [])
    r = await c.get("/api/v1/admin/announcements/unread")
    assert r.status_code == 200
    assert [i["title"] for i in r.json()["data"]["items"]] == ["全员可见"]
    # 对照：同一 staff 读管理列表仍 403（写侧权限未松动）
    assert (await c.get("/api/v1/admin/announcements")).status_code == 403
    await c.aclose()


@pytest.mark.asyncio
async def test_mark_read_clears_unread_and_is_per_user(auth, make_staff):
    a = (await _post(auth, title="只弹一次")).json()["data"]
    c = await _staff_client(auth, make_staff, "s_a", [])
    aid = a["id"]
    assert (await c.post("/api/v1/admin/announcements/read", json={"ids": [aid]})).status_code == 200
    assert (await c.get("/api/v1/admin/announcements/unread")).json()["data"]["items"] == []
    # 另一用户不受影响
    c2 = await _staff_client(auth, make_staff, "s_b", [])
    assert [i["id"] for i in (await c2.get("/api/v1/admin/announcements/unread")).json()["data"]["items"]] == [aid]
    # admin 自己也没读过
    assert len((await auth.get("/api/v1/admin/announcements/unread")).json()["data"]["items"]) == 1
    await c.aclose(); await c2.aclose()


@pytest.mark.asyncio
async def test_mark_read_idempotent(auth, make_staff):
    a = (await _post(auth, title="幂等")).json()["data"]
    c = await _staff_client(auth, make_staff, "s_idem", [])
    for _ in range(2):
        r = await c.post("/api/v1/admin/announcements/read", json={"ids": [a["id"]]})
        assert r.status_code == 200
    async with SessionLocal() as db:
        n = (await db.execute(sa_text(
            "select count(*) from announcement_reads where user_id = :u"),
            {"u": (await _uid("s_idem"))})).scalar_one()
    assert int(n) == 1
    await c.aclose()


@pytest.mark.asyncio
async def test_mark_read_tolerates_dirty_ids(auth, make_staff):
    c = await _staff_client(auth, make_staff, "s_dirty", [])
    assert (await c.post("/api/v1/admin/announcements/read", json={"ids": []})).json()["data"]["marked"] == 0
    r = await c.post("/api/v1/admin/announcements/read", json={"ids": [999999]})
    assert r.status_code == 200 and r.json()["data"]["marked"] == 0     # 不存在的 id 静默跳过
    async with SessionLocal() as db:
        total = (await db.execute(sa_text("select count(*) from announcement_reads"))).scalar_one()
    assert int(total) == 0
    await c.aclose()


@pytest.mark.asyncio
async def test_delete_announcement_cascades_reads(auth, make_staff):
    a = (await _post(auth, title="级联")).json()["data"]
    c = await _staff_client(auth, make_staff, "s_casc", [])
    r = await c.post("/api/v1/admin/announcements/read", json={"ids": [a["id"]]})
    assert r.json()["data"]["marked"] == 1                 # 先实证真写过一行，级联断言才非真空通过
    await c.aclose()
    assert (await auth.delete(f"/api/v1/admin/announcements/{a['id']}")).status_code == 200
    async with SessionLocal() as db:
        n = (await db.execute(sa_text(
            "select count(*) from announcement_reads where announcement_id = :i"),
            {"i": a["id"]})).scalar_one()
    assert int(n) == 0
