"""columns hierarchy: add parent_id (max 3 levels, app-layer validated)

Revision ID: b3d5e7f9a1c2
Revises: a2b4c6d8e0f1
Create Date: 2026-09-25 11:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d5e7f9a1c2'
down_revision: Union[str, Sequence[str], None] = 'a2b4c6d8e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("columns") as batch:
        batch.add_column(sa.Column("parent_id", sa.Integer,
                                   sa.ForeignKey("columns.id", name="fk_columns_parent_id"),
                                   nullable=True))
        batch.create_index("ix_columns_parent_id", ["parent_id"])


def downgrade() -> None:
    with op.batch_alter_table("columns") as batch:
        batch.drop_index("ix_columns_parent_id")
        batch.drop_column("parent_id")
