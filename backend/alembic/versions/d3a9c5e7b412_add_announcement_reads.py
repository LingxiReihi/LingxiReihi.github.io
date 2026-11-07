"""add announcement_reads: 逐条已读水位表（v2 登录弹窗）

v1 把公告读也钉在 announcement:manage 上，用户换 staff 账号实测发现其他管理员看不到。
v2 读全员开放 + 「看过就不再打扰」，需要一个按 (公告, 管理员) 记录的水位表。

Revision ID: d3a9c5e7b412
Revises: c9e2f4a7b108
Create Date: 2026-10-14 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a9c5e7b412'
down_revision: Union[str, Sequence[str], None] = 'c9e2f4a7b108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 列、复合主键、两侧 CASCADE 一次性写进 create_table —— SQLite 不支持建表后
    # 再 create_primary_key，分步写会在 upgrade 阶段直接失败。
    op.create_table(
        "announcement_reads",
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("announcement_id", "user_id"),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_announcement_reads_user", "announcement_reads", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_announcement_reads_user", table_name="announcement_reads")
    op.drop_table("announcement_reads")
