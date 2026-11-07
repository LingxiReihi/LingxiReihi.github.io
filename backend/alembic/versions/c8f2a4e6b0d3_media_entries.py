"""media zip entries

Revision ID: c8f2a4e6b0d3
Revises: b3d5e7f9a1c2
Create Date: 2026-09-29 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f2a4e6b0d3'
down_revision: Union[str, Sequence[str], None] = 'b3d5e7f9a1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entries', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_column('entries')
