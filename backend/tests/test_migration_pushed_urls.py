"""迁移 b8d2f5c1e304 的端到端验证：pushed_urls 建表 / 唯一索引 / 回滚。"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PREV_REV = "a7c1e4b9d260"
HEAD_REV = "b8d2f5c1e304"


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


def _indexes(db: Path, table: str) -> dict[str, bool]:
    c = sqlite3.connect(db)
    rows = c.execute(f"pragma index_list({table})").fetchall()
    c.close()
    return {r[1]: bool(r[2]) for r in rows}      # name -> unique


def test_pushed_urls_migration_up_and_down(tmp_path: Path):
    db = tmp_path / "mig.db"
    _alembic(db, PREV_REV)
    assert "pushed_urls" not in _tables(db)

    _alembic(db, HEAD_REV)
    assert "pushed_urls" in _tables(db)
    assert {"url", "first_pushed_at", "last_pushed_at", "push_count"} <= _columns(db, "pushed_urls")
    # url 唯一索引（去重依据）
    assert any(uniq for name, uniq in _indexes(db, "pushed_urls").items() if "url" in name)

    # 唯一约束真的生效
    c = sqlite3.connect(db)
    c.execute("insert into pushed_urls (url, first_pushed_at, last_pushed_at, push_count) "
              "values ('https://example.com/a', '2026-11-03 00:00:00', '2026-11-03 00:00:00', 1)")
    try:
        c.execute("insert into pushed_urls (url, first_pushed_at, last_pushed_at, push_count) "
                  "values ('https://example.com/a', '2026-11-03 00:00:00', '2026-11-03 00:00:00', 1)")
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    c.close()
    assert raised

    _alembic(db, PREV_REV, command="downgrade")
    assert "pushed_urls" not in _tables(db)
