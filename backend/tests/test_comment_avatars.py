"""评论头像走本地开源图包（DiceBear Open Peeps，设计 CC0）：出参形态、按邮箱稳定、图包与常量对齐。"""
import re
from pathlib import Path

from app.core.text import AVATAR_COUNT, comment_avatar_url

AVATAR_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "avatars"


def test_every_slot_the_url_function_emits_has_a_file():
    files = {f.name for f in AVATAR_DIR.glob("*.svg")}
    assert len(files) == AVATAR_COUNT
    for i in range(AVATAR_COUNT):
        assert (AVATAR_DIR / f"{i:02d}.svg").exists()


def test_same_email_is_stable_regardless_of_case_and_spaces():
    a = comment_avatar_url("Bob@Example.com")
    assert a == comment_avatar_url("bob@example.com") == comment_avatar_url("  BOB@example.COM  ")
    assert re.fullmatch(r"/avatars/\d{2}\.svg", a)


def test_different_emails_spread_over_the_pack():
    got = {comment_avatar_url(f"u{i}@example.com") for i in range(40)}
    assert len(got) > 20


async def _approve_one(client, auth, email):
    """种内容 → 提交一条该邮箱的评论 → 审核通过，返回 (前台那条, 后台那条)。"""
    from app.api import comments as cmod
    from tests.test_public import seed_contents
    cmod._submit_cooldown.clear()
    await seed_contents()
    det = (await client.get("/api/v1/posts/post-one")).json()["data"]
    await client.post("/api/v1/comments", json={
        "content_id": det["id"], "nickname": "小明", "email": email, "body": "写得好！"})
    cid = (await auth.get("/api/v1/admin/comments?status=pending")).json()["data"]["items"][0]["id"]
    await auth.post("/api/v1/admin/comments/moderate",
                    json={"ids": [cid], "status": "approved"})
    pub = (await client.get(f"/api/v1/comments?content_id={det['id']}")).json()["data"]["items"][0]
    adm = (await auth.get("/api/v1/admin/comments")).json()["data"]["items"][0]
    return pub, adm


async def _set_admin_identity(email, avatar):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import User
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
        u.email, u.avatar_url = email, avatar
        await db.commit()


async def test_public_and_admin_lists_both_use_pack_avatar(client, auth):
    pub, adm = await _approve_one(client, auth, "xiaoming@example.com")
    for item in (pub, adm):
        assert re.fullmatch(r"/avatars/\d{2}\.svg", item["avatar"])
        assert "gravatar" not in item["avatar"]
    assert pub["avatar"] == adm["avatar"] == comment_avatar_url("xiaoming@example.com")


async def test_admin_email_gets_the_admin_profile_avatar(client, auth):
    await _set_admin_identity("admin@example.com", "/media/avatar/2026/10/mine.png")
    pub, adm = await _approve_one(client, auth, "admin@example.com")
    assert pub["avatar"] == adm["avatar"] == "/media/avatar/2026/10/mine.png"


async def test_match_ignores_case_and_surrounding_spaces(client, auth):
    await _set_admin_identity("admin@example.com", "/media/avatar/2026/10/mine.png")
    pub, _ = await _approve_one(client, auth, "  ADMIN@Example.com ")
    assert pub["avatar"] == "/media/avatar/2026/10/mine.png"


async def test_admin_without_uploaded_avatar_falls_back_to_pack(client, auth):
    await _set_admin_identity("admin@example.com", None)
    pub, _ = await _approve_one(client, auth, "admin@example.com")
    assert pub["avatar"] == comment_avatar_url("admin@example.com")


async def test_other_admins_avatars_do_not_leak(client, auth):
    await _set_admin_identity("admin@example.com", "/media/avatar/2026/10/mine.png")
    pub, _ = await _approve_one(client, auth, "xiaoming@example.com")
    assert pub["avatar"] == comment_avatar_url("xiaoming@example.com")
    assert "mine.png" not in pub["avatar"]
