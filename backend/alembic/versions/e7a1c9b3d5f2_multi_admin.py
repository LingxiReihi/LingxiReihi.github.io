"""multi admin accounts, permission grants and content ownership

Revision ID: e7a1c9b3d5f2
Revises: d9b3c5e7f0a2
Create Date: 2026-10-03 12:36:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.core.db


# revision identifiers, used by Alembic.
revision: str = 'e7a1c9b3d5f2'
down_revision: Union[str, Sequence[str], None] = 'd9b3c5e7f0a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPER_ID_SUBQUERY = "(SELECT id FROM users WHERE role='super' ORDER BY id LIMIT 1)"


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=16), nullable=False,
                                      server_default='staff'))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False,
                                      server_default='1'))
        batch_op.add_column(sa.Column('note', sa.String(length=128), nullable=False,
                                      server_default=''))
        batch_op.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_users_created_by_id', 'users', ['created_by_id'], ['id'],
                                    ondelete='SET NULL')

    # 最早的账号（seed 出来的站点主账号）即顶级管理员；其余按 staff 走授权表
    op.execute("UPDATE users SET role='super' WHERE id = (SELECT MIN(id) FROM users)")

    op.create_table('admin_grants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('permission', sa.String(length=32), nullable=False),
    sa.Column('scope_type', sa.String(length=16), nullable=False),
    sa.Column('scope_id', sa.Integer(), nullable=True),
    sa.Column('granted_by', sa.Integer(), nullable=True),
    sa.Column('created_at', app.core.db.TZDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['granted_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'permission', 'scope_type', 'scope_id', name='uq_admin_grant')
    )
    op.create_index('ix_admin_grants_user_id', 'admin_grants', ['user_id'], unique=False)

    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_contents_created_by_id', 'users', ['created_by_id'],
                                    ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_contents_created_by_id', ['created_by_id'], unique=False)

    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uploaded_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_media_assets_uploaded_by_id', 'users', ['uploaded_by_id'],
                                    ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_media_assets_uploaded_by_id', ['uploaded_by_id'], unique=False)

    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reviewed_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_comments_reviewed_by_id', 'users', ['reviewed_by_id'],
                                    ['id'], ondelete='SET NULL')

    # 回填：现存内容/素材全部归顶级管理员 → super 绕过校验，线上行为零回归
    op.execute(f"UPDATE contents SET created_by_id = {SUPER_ID_SUBQUERY} "
               "WHERE created_by_id IS NULL")
    op.execute(f"UPDATE media_assets SET uploaded_by_id = {SUPER_ID_SUBQUERY} "
               "WHERE uploaded_by_id IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_column('reviewed_by_id')

    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_index('ix_media_assets_uploaded_by_id')
        batch_op.drop_column('uploaded_by_id')

    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.drop_index('ix_contents_created_by_id')
        batch_op.drop_column('created_by_id')

    op.drop_index('ix_admin_grants_user_id', table_name='admin_grants')
    op.drop_table('admin_grants')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_created_by_id', type_='foreignkey')
        batch_op.drop_column('created_by_id')
        batch_op.drop_column('note')
        batch_op.drop_column('is_active')
        batch_op.drop_column('role')
