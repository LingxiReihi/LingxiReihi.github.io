"""content likes

Revision ID: c4e8a1b09f72
Revises: b7c1f0a9d2e4
Create Date: 2026-09-22 21:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1b09f72'
down_revision: Union[str, Sequence[str], None] = 'b7c1f0a9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('likes', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.drop_column('likes')
