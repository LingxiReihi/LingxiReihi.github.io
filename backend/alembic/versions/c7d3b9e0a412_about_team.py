"""about team: users.show_in_about —— About 页「管理团队」名单的露出开关

Revision ID: c7d3b9e0a412
Revises: a8c1e4f7b205
Create Date: 2026-10-06 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d3b9e0a412'
down_revision: Union[str, Sequence[str], None] = 'a8c1e4f7b205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 默认 0 = 零新增暴露面：升级后 About 名单为空，和改造前逐字一致。
    # super 那行置 1 只是让它与「主体本来就在 About 上」的现状对齐；
    # 名单查询本身排除 super，所以这一列对顶级管理员不产生行为。
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('show_in_about', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET show_in_about = 1 WHERE role = 'super'"))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('show_in_about')
