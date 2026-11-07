"""comments table

Revision ID: d5f2b8c3a901
Revises: c4e8a1b09f72
Create Date: 2026-09-22 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.core.db


# revision identifiers, used by Alembic.
revision: str = 'd5f2b8c3a901'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1b09f72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('content_id', sa.Integer(), nullable=False),
    sa.Column('nickname', sa.String(length=50), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('submit_ip', sa.String(length=45), nullable=False),
    sa.Column('created_at', app.core.db.TZDateTime(timezone=True), nullable=False),
    sa.Column('reviewed_at', app.core.db.TZDateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['content_id'], ['contents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_comments_content_id'), 'comments', ['content_id'], unique=False)
    op.create_index(op.f('ix_comments_status'), 'comments', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_comments_status'), table_name='comments')
    op.drop_index(op.f('ix_comments_content_id'), table_name='comments')
    op.drop_table('comments')
