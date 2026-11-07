"""media category

Revision ID: b7c1f0a9d2e4
Revises: a3333c91a605
Create Date: 2026-09-22 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1f0a9d2e4'
down_revision: Union[str, Sequence[str], None] = 'a3333c91a605'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=16), nullable=True))
        batch_op.create_index(batch_op.f('ix_media_assets_category'), ['category'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_assets_category'))
        batch_op.drop_column('category')
