"""columns per-type isolation: add type column, unique (type,name)/(type,slug)

Revision ID: a2b4c6d8e0f1
Revises: f1c3d5e7a9b1
Create Date: 2026-09-25 02:20:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2b4c6d8e0f1'
down_revision: Union[str, Sequence[str], None] = 'f1c3d5e7a9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """CREATE TABLE columns_new (
               id INTEGER PRIMARY KEY,
               name VARCHAR(64) NOT NULL,
               slug VARCHAR(128) NOT NULL,
               type VARCHAR(16) NOT NULL DEFAULT 'article',
               summary TEXT NOT NULL DEFAULT '',
               sort_order INTEGER NOT NULL DEFAULT 0,
               created_at DATETIME,
               updated_at DATETIME,
               UNIQUE (type, name),
               UNIQUE (type, slug)
           )"""
    )
    # 现有栏目全部归入 article（此前仅文章可挂栏目）
    conn.exec_driver_sql(
        """INSERT INTO columns_new (id, name, slug, type, summary, sort_order, created_at, updated_at)
           SELECT id, name, slug, 'article', summary, sort_order, created_at, updated_at FROM columns"""
    )
    conn.exec_driver_sql("DROP TABLE columns")
    conn.exec_driver_sql("ALTER TABLE columns_new RENAME TO columns")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """CREATE TABLE columns_legacy (
               id INTEGER PRIMARY KEY,
               name VARCHAR(64) NOT NULL UNIQUE,
               slug VARCHAR(128) NOT NULL UNIQUE,
               summary TEXT NOT NULL DEFAULT '',
               sort_order INTEGER NOT NULL DEFAULT 0,
               created_at DATETIME,
               updated_at DATETIME
           )"""
    )
    conn.exec_driver_sql(
        """INSERT INTO columns_legacy (id, name, slug, summary, sort_order, created_at, updated_at)
           SELECT id, name, slug, summary, sort_order, created_at, updated_at FROM columns WHERE type = 'article'"""
    )
    conn.exec_driver_sql("DROP TABLE columns")
    conn.exec_driver_sql("ALTER TABLE columns_legacy RENAME TO columns")
