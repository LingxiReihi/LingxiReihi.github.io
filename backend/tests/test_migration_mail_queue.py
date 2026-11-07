"""迁移 e2b5d7f9a4c1 的端到端验证：跑真 alembic 链，不靠读代码断言。"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PREV_REV = "d1f4a6c8b307"
HEAD_REV = "e2b5d7f9a4c1"


def _alembic(db: Path, rev: str, *, command: str = "upgrade") -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    r = subprocess.run([sys.executable, "-m", "alembic", command, rev], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _tables(db: Path) -> set[str]:
    c = sqlite3.connect(db)
    names = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    c.close()
    return names


def _columns(db: Path, table: str) -> set[str]:
    c = sqlite3.connect(db)
    cols = {r[1] for r in c.execute(f"pragma table_info({table})")}
    c.close()
    return cols


def test_mail_queue_migration_up_and_down(tmp_path: Path):
    db = tmp_path / "mig.db"
    _alembic(db, PREV_REV)
    assert "mail_queue" not in _tables(db)
    assert "notified_at" not in _columns(db, "comments")
    c = sqlite3.connect(db)
    c.execute("INSERT INTO comments (content_id, nickname, email, body, status, submit_ip,"
              " created_at) VALUES (1,'小明','a@x.test','正文','pending','','2026-10-06 00:00:00')")
    c.commit()
    c.close()

    _alembic(db, HEAD_REV)
    assert "mail_queue" in _tables(db)
    assert {"to_addr", "subject", "body_text", "kind", "status", "attempts", "last_error",
            "comment_id", "next_try_at"} <= _columns(db, "mail_queue")
    assert "notified_at" in _columns(db, "comments")
    c = sqlite3.connect(db)
    c.execute("INSERT INTO mail_queue (to_addr, subject, body_text, kind, status, attempts,"
              " last_error, next_try_at, created_at, updated_at) "
              "VALUES ('a@x.test','标题','正文','comment_author','pending',0,'',"
              "'2026-10-06 00:00:00','2026-10-06 00:00:00','2026-10-06 00:00:00')")
    assert c.execute("select count(*) from mail_queue").fetchone()[0] == 1
    assert c.execute("select count(*) from comments").fetchone()[0] == 1     # 老评论行没被牵连
    c.close()

    _alembic(db, PREV_REV, command="downgrade")
    assert "mail_queue" not in _tables(db)
    assert "notified_at" not in _columns(db, "comments")
    assert sqlite3.connect(db).execute("select count(*) from comments").fetchone()[0] == 1
