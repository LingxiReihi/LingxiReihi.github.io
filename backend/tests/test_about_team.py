"""About「管理团队」名单：凡启用的管理员都露出（show_in_about 已作废），公开字段四项白名单。"""
import asyncio
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import RebuildJob, User

BACKEND = Path(__file__).resolve().parents[1]
ADD_REV = "c7d3b9e0a412"        # 曾加过 show_in_about
DROP_REV = "d1f4a6c8b307"       # 作废它：前滚删列


async def _login_as(client, username, password="staff-pass-123"):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()["data"]["access_token"]}"


async def _team(client) -> list[dict]:
    r = await client.get("/api/v1/about")
    assert r.status_code == 200, r.text
    return r.json()["data"]["team"]


async def _job_count() -> int:
    async with SessionLocal() as db:
        return len((await db.execute(select(RebuildJob))).scalars().all())


# ---------- 露出规则 ----------

async def test_every_active_admin_shows_up_with_no_setup(client, auth, make_staff):
    """新口径：建号即上名单，不需要任何勾选动作。"""
    await make_staff("auto", nickname="自动上榜的人")
    assert [x["nickname"] for x in await _team(client)] == ["自动上榜的人"]


async def test_super_is_the_header_and_not_in_the_team(client, auth, make_staff):
    await auth.put("/api/v1/admin/profile", json={"nickname": "站长"})
    await make_staff("helper", nickname="帮手")
    d = (await client.get("/api/v1/about")).json()["data"]
    assert d["nickname"] == "站长"
    assert [x["nickname"] for x in d["team"]] == ["帮手"], "super 不重复进名单（同页两遍）"


async def test_deactivated_admin_drops_off_and_queues_rebuild(client, auth, make_staff):
    m = await make_staff("ghost", nickname="要下架的人")
    assert [x["nickname"] for x in await _team(client)] == ["要下架的人"]
    before = await _job_count()
    await auth.put(f"/api/v1/admin/admins/{m['id']}", json={"is_active": False})
    assert await _team(client) == [], "停用即从公开名单下架"
    await asyncio.sleep(0.3)
    assert await _job_count() > before, "About 是预渲染页，下架必须入队重建"


async def test_team_orders_by_id(client, auth, make_staff):
    second = await make_staff("b_second", nickname="乙")
    first = await make_staff("a_first", nickname="甲")
    assert [x["nickname"] for x in await _team(client)] == ["乙", "甲"]
    assert second["id"] < first["id"]


# ---------- 公开字段白名单 ----------

async def test_team_members_carry_the_full_profile_but_never_privates(client, auth, make_staff):
    """卡片要和 admin 那份同布局，所以成员也得带 bio/技能/经历；身份类字段仍一律不外发。"""
    m = await make_staff("shown", nickname="展示位", email="shown-secret@example.test")
    await auth.put(f"/api/v1/admin/admins/{m['id']}",
                   json={"avatar": "/media/s.png", "signature": "只写一句话",
                         "bio_md": "白天写代码", "skills": [{"group": "前端", "items": ["Vue"]}],
                         "experience": [{"kind": "edu", "title": "某大学"}],
                         "social_links": [{"platform": "GitHub", "url": "https://github.com/s"}]})
    assert await _team(client) == [{
        "nickname": "展示位", "avatar": "/media/s.png", "signature": "只写一句话",
        "bio_md": "白天写代码", "skills": [{"group": "前端", "items": ["Vue"]}],
        "experience": [{"kind": "edu", "title": "某大学"}],
        "social_links": [{"platform": "GitHub", "url": "https://github.com/s"}]}]
    body = str((await client.get("/api/v1/about")).json())
    assert "shown-secret@example.test" not in body
    assert not ({"email", "username", "role", "note", "is_active", "id"} & set((await _team(client))[0]))


async def test_blank_nickname_falls_back_to_username(client, auth, make_staff):
    """昵称被清空也不能出现空卡片。"""
    m = await make_staff("nobody", nickname="占位")
    await auth.put(f"/api/v1/admin/admins/{m['id']}", json={"nickname": ""})
    assert [x["nickname"] for x in await _team(client)] == ["nobody"]


# ---------- 预渲染联动 ----------

async def test_member_self_edit_queues_about_rebuild(client, auth, make_staff):
    """成员必然在名单里，所以改自己资料也要重建 About（不再有「没露出就不建」的分支）。"""
    await make_staff("writer", nickname="写稿人")
    await _login_as(client, "writer")
    before = await _job_count()
    r = await client.put("/api/v1/admin/profile", json={"signature": "改一行签名"})
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)
    assert await _job_count() > before


async def test_super_bio_edit_queues_rebuild(client, auth, make_staff):
    before = await _job_count()
    r = await auth.put("/api/v1/admin/profile", json={"bio_md": "新简介"})
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)
    assert await _job_count() > before


# ---------- show_in_about 作废 ----------

async def test_show_in_about_is_gone(client, auth, make_staff):
    """列已删、请求体不再认这个字段：单独带它等于「没有需要变更的字段」，混着带则被忽略。"""
    m = await make_staff("flagged", nickname="带开关的请求")
    r = await auth.put(f"/api/v1/admin/admins/{m['id']}", json={"show_in_about": False})
    assert r.status_code == 400, r.text
    r = await auth.put(f"/api/v1/admin/admins/{m['id']}",
                       json={"note": "开关应被忽略", "show_in_about": False})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["note"] == "开关应被忽略"
    assert "show_in_about" not in r.json()["data"]
    assert [x["nickname"] for x in await _team(client)] == ["带开关的请求"]
    assert "show_in_about" not in User.__table__.columns


# ---------- 迁移：前滚删列 ----------

def _alembic(db: Path, rev: str, direction: str = "upgrade") -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    r = subprocess.run([sys.executable, "-m", "alembic", direction, rev], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _user_cols(db: Path) -> list[str]:
    c = sqlite3.connect(db)
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
    c.close()
    return cols


def test_drop_migration_removes_the_abandoned_column(tmp_path):
    db = tmp_path / "mig4.db"
    _alembic(db, ADD_REV)
    assert "show_in_about" in _user_cols(db)          # 曾被加过
    _alembic(db, DROP_REV)
    assert "show_in_about" not in _user_cols(db), "作废的开关列必须真的消失"
    assert "signature" in _user_cols(db), "别把上一批的资料列一起删了"
    _alembic(db, ADD_REV, "downgrade")
    assert "show_in_about" in _user_cols(db)          # 回退能重建该列
