"""admin account email

Revision ID: f4a8c2d6e9b3
Revises: e7a1c9b3d5f2
Create Date: 2026-10-04 00:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a8c2d6e9b3'
down_revision: Union[str, Sequence[str], None] = 'e7a1c9b3d5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 列保持 nullable：建号起必填，但已存在的账号（seed 出的顶级管理员）无邮箱，
    # 唯一索引下多个 NULL 互不冲突，不必给它们编邮箱。
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email')
