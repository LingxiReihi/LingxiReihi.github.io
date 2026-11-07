"""个人资料跟人走：自助改自己、super 代改他人、公开署名白名单、profile 组退役。"""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Content, User


async def _me(client) -> dict:
    r = await client.get("/api/v1/admin/auth/me")
    return r.json()["data"]


async def _as(client, username, password):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"


async def _uid(client, username) -> int:
    rows = (await client.get("/api/v1/admin/admins")).json()["data"]["items"]
    return next(x["id"] for x in rows if x["username"] == username)


# ---------- 自助 ----------

async def test_zero_perm_staff_can_edit_own_profile(client, auth, make_staff):
    """改自己资料不需要任何权限点（setting:manage 只管站点设置）。"""
    made = await make_staff("staff1")
    await _as(client, "staff1", "staff-pass-123")
    assert (await _me(client))["permissions"] == []
    r = await client.put("/api/v1/admin/profile", json={
        "nickname": "小张", "avatar": "/media/blog/2026/10/x.png", "signature": "写点东西",
        "social_links": [{"platform": "GitHub", "url": "https://github.com/z"}]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["nickname"] == "小张"
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == made["id"]))).scalar_one()
        assert u.nickname == "小张" and u.avatar_url.endswith("x.png")
        assert u.signature == "写点东西" and u.social_links[0]["platform"] == "GitHub"


async def test_my_profile_offers_the_same_fields_to_everyone(client, auth, make_staff):
    """资料字段不再分 super/staff：每人管自己那一份（越界靠「只能改自己」兜）。"""
    await make_staff("staff1")
    await _as(client, "staff1", "staff-pass-123")
    mine = (await client.get("/api/v1/admin/profile")).json()["data"]
    assert mine["is_super"] is False
    assert set(mine["editable"]) == {"nickname", "avatar", "signature", "social_links",
                                     "bio_md", "skills", "experience"}
    await _as(client, "admin", "test-pass-123")
    sup = (await client.get("/api/v1/admin/profile")).json()["data"]
    assert sup["is_super"] is True and set(sup["editable"]) == set(mine["editable"])


async def test_staff_can_edit_own_career_fields_and_it_reaches_about(client, auth, make_staff):
    """零权限 staff 也能填自己的简介/技能/经历——它们现在会渲染进他那张公开卡片。"""
    await make_staff("staff1", nickname="小张")
    await _as(client, "staff1", "staff-pass-123")
    r = await client.put("/api/v1/admin/profile", json={
        "bio_md": "白天运维，晚上渲染",
        "skills": [{"group": "运维", "items": ["Docker", "Caddy"]}],
        "experience": [{"kind": "work", "title": "运维工程师", "org": "某厂",
                        "start": "2023-01", "end": None, "desc": "站点与备份"}]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["bio_md"] == "白天运维，晚上渲染"
    assert d["skills"][0]["items"] == ["Docker", "Caddy"]
    assert d["experience"][0]["title"] == "运维工程师"
    member = next(m for m in (await client.get("/api/v1/about")).json()["data"]["team"]
                  if m["nickname"] == "小张")
    assert member["skills"][0]["group"] == "运维"
    assert member["experience"][0]["org"] == "某厂"


async def test_profile_service_still_rejects_non_profile_keys(client, auth):
    """HTTP 层被 schema 挡住，服务层的白名单是机制级兜底（防将来开 extra=allow 或新调用方）。"""
    import pytest as _pytest

    from app.core.db import SessionLocal as _SL
    from app.services import profiles

    async with _SL() as db:
        u = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
        for key in ("email", "role", "is_active", "password", "username", "id"):
            with _pytest.raises(ValueError):
                await profiles.update_profile(db, u, {key: "x"})


async def test_super_profile_edit_drives_about(client, auth):
    await auth.put("/api/v1/admin/profile", json={"nickname": "站长本人", "signature": "sig-super"})
    d = (await client.get("/api/v1/about")).json()["data"]
    assert d["nickname"] == "站长本人" and d["signature"] == "sig-super"
    cfg = (await client.get("/api/v1/admin/auth/me")).json()  # 仅确认 admin 会话仍在
    assert cfg["data"]["is_super"] is True


# ---------- 代改他人 ----------

async def test_only_super_can_edit_others_profile(client, auth, make_staff):
    victim = await make_staff("victim")
    await make_staff("gatekeeper", grants=[{"permission": "admin:manage"}])
    await _as(client, "gatekeeper", "staff-pass-123")
    r = await client.put(f"/api/v1/admin/admins/{victim['id']}",
                         json={"avatar": "/media/a.png", "signature": "替他改"})
    assert r.status_code == 403 and "顶级管理员" in r.json()["message"]
    await _as(client, "admin", "test-pass-123")
    r = await client.put(f"/api/v1/admin/admins/{victim['id']}",
                         json={"avatar": "/media/a.png", "signature": "替他改"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["signature"] == "替他改"


# ---------- 公开署名与隐私 ----------

async def test_public_detail_author_whitelist(client, auth, make_staff):
    """公开 DTO 只给 nickname/avatar：email/username/role/note 一律不外发。"""
    await make_staff("writer", nickname="写稿人", grants=[{"permission": "content:write"}])
    await _as(client, "writer", "staff-pass-123")
    await client.put("/api/v1/admin/profile",
                     json={"avatar": "/media/writer.png", "signature": "签名"})
    made = (await client.post("/api/v1/admin/contents", json={
        "type": "article", "status": "published", "title": "署名测试", "body_md": "正文"
    })).json()["data"]
    await _as(client, "admin", "test-pass-123")
    await client.patch(f"/api/v1/admin/contents/{made['id']}/status", json={"status": "published"})
    pub = await client.get(f"/api/v1/posts/{made['slug']}")
    author_out = pub.json()["data"]["author"]
    assert author_out == {"nickname": "写稿人", "avatar": "/media/writer.png"}
    assert not ({"email", "username", "role", "note", "id", "is_active"} & set(author_out))
    assert "writer@example.test" not in pub.text        # 邮箱绝不出现在公开响应里


async def test_author_falls_back_to_super_when_missing_or_inactive(client, auth, make_staff):
    await auth.put("/api/v1/admin/profile", json={"nickname": "站长"})
    c = await auth.post("/api/v1/admin/contents", json={
        "type": "article", "status": "published", "title": "无主稿", "body_md": "x"})
    cid = c.json()["data"]["id"]
    async with SessionLocal() as db:
        row = (await db.execute(select(Content).where(Content.id == cid))).scalar_one()
        row.created_by_id = None
        await db.commit()
    pub = await client.get(f"/api/v1/posts/{c.json()['data']['slug']}")
    assert pub.json()["data"]["author"]["nickname"] == "站长"

    ghost = await make_staff("ghost", nickname="幽灵", grants=[{"permission": "content:write"}])
    await _as(client, "ghost", "staff-pass-123")
    own = await client.post("/api/v1/admin/contents", json={
        "type": "article", "status": "published", "title": "停用者的稿", "body_md": "x"})
    await _as(client, "admin", "test-pass-123")
    await client.put(f"/api/v1/admin/admins/{ghost['id']}", json={"is_active": False})
    pub = await client.get(f"/api/v1/posts/{own.json()['data']['slug']}")
    assert pub.json()["data"]["author"]["nickname"] == "站长"


# ---------- 旧站点级 profile 组确认退役 ----------

async def test_settings_profile_group_retired(client, auth):
    assert (await client.put("/api/v1/admin/settings/profile",
                             json={"nickname": "回退尝试"})).json()["code"] == 40000
    groups = (await client.get("/api/v1/admin/settings")).json()["data"]
    assert "profile" not in groups
    async with SessionLocal() as db:
        from app.models import SiteSetting
        assert (await db.execute(select(SiteSetting).where(
            SiteSetting.key.like("profile.%")))).scalars().all() == []
