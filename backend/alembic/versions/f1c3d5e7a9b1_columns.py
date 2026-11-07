"""columns table + contents.column_id (栏目分组)

Revision ID: f1c3d5e7a9b1
Revises: e6a9c2d4f810
Create Date: 2026-09-25 01:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1c3d5e7a9b1'
down_revision: Union[str, Sequence[str], None] = 'e6a9c2d4f810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS columns (
               id INTEGER PRIMARY KEY,
               name VARCHAR(64) NOT NULL UNIQUE,
               slug VARCHAR(128) NOT NULL UNIQUE,
               summary TEXT NOT NULL DEFAULT '',
               sort_order INTEGER NOT NULL DEFAULT 0,
               created_at DATETIME,
               updated_at DATETIME
           )"""
    )
    with op.batch_alter_table("contents") as batch:
        batch.add_column(sa.Column("column_id", sa.Integer,
                                   sa.ForeignKey("columns.id", name="fk_contents_column_id"),
                                   nullable=True))
        batch.create_index("ix_contents_column_id", ["column_id"])


def downgrade() -> None:
    with op.batch_alter_table("contents") as batch:
        batch.drop_index("ix_contents_column_id")
        batch.drop_column("column_id")
    op.execute("DROP TABLE columns")
