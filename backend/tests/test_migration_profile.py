"""迁移 a8c1e4f7b205 的端到端验证：跑真 alembic 链，不靠读代码断言。"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PREV_REV = "f4a8c2d6e9b3"
HEAD_REV = "a8c1e4f7b205"

OLD_PROFILE = {
    "profile.nickname": "泠曦",
    "profile.avatar": "/media/avatar/2026/09/d4b5.jpg",
    "profile.signature": "雨雪天潭深千尺",
    "profile.bio_md": "正文**markdown**",
    "profile.social_links": [{"platform": "CSDN", "url": "https://blog.csdn.net/x"}],
    "profile.skills": [],
    "profile.experience": [{"kind": "edu", "title": "计算机科学与技术"}],
}


def _alembic(db: Path, rev: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", rev], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _seed(db: Path, *, account_nickname: str) -> None:
    c = sqlite3.connect(db)
    c.execute("INSERT INTO users (username, password_hash, nickname, avatar_url, role, is_active,"
              " failed_attempts, token_version, created_at) VALUES "
              "('admin','x',?,NULL,'super',1,0,0,'2026-10-04 00:00:00')", (account_nickname,))
    for key, value in OLD_PROFILE.items():
        c.execute("INSERT INTO site_settings (key, value, updated_at) VALUES (?, ?, ?)",
                  (key, json.dumps(value, ensure_ascii=False), "2026-10-04 00:00:00"))
    c.commit()
    c.close()


def _state(db: Path) -> tuple[dict, list[str]]:
    c = sqlite3.connect(db)
    cols = ("nickname", "avatar_url", "signature", "bio_md", "social_links", "skills", "experience")
    row = c.execute(f"SELECT {', '.join(cols)} FROM users WHERE role='super'").fetchone()
    left = [r[0] for r in c.execute("SELECT key FROM site_settings WHERE key LIKE 'profile.%'")]
    c.close()
    return dict(zip(cols, row)), left


def test_profile_moves_to_super_when_nickname_not_deliberately_set(tmp_path):
    db = tmp_path / "mig.db"
    _alembic(db, PREV_REV)
    _seed(db, account_nickname="admin")       # 昵称等于登录名 → 视为没设过
    _alembic(db, HEAD_REV)

    profile, leftovers = _state(db)
    assert profile["nickname"] == "泠曦", "站点旧昵称没接管 → About 会退化成 admin"
    assert profile["avatar_url"] == OLD_PROFILE["profile.avatar"]
    assert profile["signature"] == "雨雪天潭深千尺"
    assert profile["bio_md"] == "正文**markdown**"
    assert json.loads(profile["social_links"])[0]["platform"] == "CSDN"
    assert json.loads(profile["experience"])[0]["kind"] == "edu"
    assert profile["skills"] is None, "空列表不该占位写入"
    assert leftovers == [], "旧 profile.* 键没清干净"

    # 回退：资料应回到全局组，且列被删掉
    r = subprocess.run([sys.executable, "-m", "alembic", "downgrade", PREV_REV], cwd=BACKEND,
                       env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    c = sqlite3.connect(db)
    back = dict(c.execute("SELECT key, value FROM site_settings WHERE key LIKE 'profile.%'"))
    assert json.loads(back["profile.nickname"]) == "泠曦"
    assert json.loads(back["profile.social_links"])[0]["platform"] == "CSDN"
    assert "signature" not in [r[1] for r in c.execute("PRAGMA table_info(users)")]
    c.close()


def test_profile_does_not_clobber_a_deliberate_nickname(tmp_path):
    db = tmp_path / "mig2.db"
    _alembic(db, PREV_REV)
    _seed(db, account_nickname="自定义昵称")     # 账号自己设过的昵称优先，不被站点旧值覆盖
    _alembic(db, HEAD_REV)
    profile, _ = _state(db)
    assert profile["nickname"] == "自定义昵称"
    assert profile["signature"] == "雨雪天潭深千尺"
