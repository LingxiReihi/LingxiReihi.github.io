"""pushed_urls: 记录已推送过的地址，避免重复推送

Revision ID: b8d2f5c1e304
Revises: a7c1e4b9d260
Create Date: 2026-11-03 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.core.db

revision: str = 'b8d2f5c1e304'
down_revision: Union[str, Sequence[str], None] = 'a7c1e4b9d260'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pushed_urls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('first_pushed_at', app.core.db.TZDateTime(timezone=True), nullable=False),
        sa.Column('last_pushed_at', app.core.db.TZDateTime(timezone=True), nullable=False),
        sa.Column('push_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pushed_urls_url'), 'pushed_urls', ['url'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_pushed_urls_url'), table_name='pushed_urls')
    op.drop_table('pushed_urls')
