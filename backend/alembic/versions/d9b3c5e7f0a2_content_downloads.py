"""content downloads counter

Revision ID: d9b3c5e7f0a2
Revises: c8f2a4e6b0d3
Create Date: 2026-09-29 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9b3c5e7f0a2'
down_revision: Union[str, Sequence[str], None] = 'c8f2a4e6b0d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('downloads', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.drop_column('downloads')
