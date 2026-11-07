"""tag type isolation: split shared tags per content type, unique (type,name)/(type,slug)

Revision ID: e6a9c2d4f810
Revises: d5f2b8c3a901
Create Date: 2026-09-23 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e6a9c2d4f810'
down_revision: Union[str, Sequence[str], None] = 'd5f2b8c3a901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """CREATE TABLE tags_new (
               id INTEGER PRIMARY KEY,
               name VARCHAR(64) NOT NULL,
               slug VARCHAR(64) NOT NULL,
               type VARCHAR(16) NOT NULL,
               UNIQUE (type, name),
               UNIQUE (type, slug)
           )"""
    )
    # 每个旧 tag 按其被使用的每种内容类型各复制一行；无引用的孤儿 tag 归入 article
    new_id: dict[tuple[int, str], int] = {}
    for tid, name, slug in conn.exec_driver_sql("SELECT id, name, slug FROM tags").fetchall():
        types = [r[0] for r in conn.exec_driver_sql(
            "SELECT DISTINCT c.type FROM content_tags ct JOIN contents c ON c.id = ct.content_id "
            "WHERE ct.tag_id = :t", {"t": tid}).fetchall()] or ["article"]
        for ty in types:
            conn.exec_driver_sql("INSERT INTO tags_new (name, slug, type) VALUES (:n, :s, :ty)",
                                 {"n": name, "s": slug, "ty": ty})
            new_id[(tid, ty)] = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
    links = conn.exec_driver_sql(
        "SELECT ct.content_id, ct.tag_id, c.type FROM content_tags ct "
        "JOIN contents c ON c.id = ct.content_id").fetchall()
    conn.exec_driver_sql("DELETE FROM content_tags")
    for cid, tid, cty in links:
        conn.exec_driver_sql("INSERT INTO content_tags (content_id, tag_id) VALUES (:c, :t)",
                             {"c": cid, "t": new_id[(tid, cty)]})
    conn.exec_driver_sql("DROP TABLE tags")
    conn.exec_driver_sql("ALTER TABLE tags_new RENAME TO tags")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """CREATE TABLE tags_legacy (
               id INTEGER PRIMARY KEY,
               name VARCHAR(64) NOT NULL UNIQUE,
               slug VARCHAR(64) NOT NULL UNIQUE
           )"""
    )
    keep: dict[int, int] = {}  # typed row id -> merged row id
    merged: dict[str, int] = {}
    for tid, name, slug in conn.exec_driver_sql(
            "SELECT id, name, slug FROM tags ORDER BY type, id").fetchall():
        if name in merged:
            keep[tid] = merged[name]
            continue
        conn.exec_driver_sql("INSERT INTO tags_legacy (name, slug) VALUES (:n, :s)",
                             {"n": name, "s": slug})
        nid = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
        merged[name] = nid
        keep[tid] = nid
    rows = conn.exec_driver_sql("SELECT content_id, tag_id FROM content_tags").fetchall()
    conn.exec_driver_sql("DELETE FROM content_tags")
    seen = set()
    for cid, tid in rows:
        pair = (cid, keep[tid])
        if pair in seen:
            continue
        seen.add(pair)
        conn.exec_driver_sql("INSERT INTO content_tags (content_id, tag_id) VALUES (:c, :t)",
                             {"c": cid, "t": pair[1]})
    conn.exec_driver_sql("DROP TABLE tags")
    conn.exec_driver_sql("ALTER TABLE tags_legacy RENAME TO tags")
