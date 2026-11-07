"""add announcements: 后台更新公告表（本期仅仪表盘消费）

用户要求「后台添加更新公告功能，并合并到仪表盘页面」。选独立表而非 site_settings 新组：
逐条 id/时间戳/排序可控、量大不失控，status 为以后接前台预留（届时无新迁移）。

Revision ID: c9e2f4a7b108
Revises: b7f3d2c8a5e4
Create Date: 2026-10-14 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e2f4a7b108'
down_revision: Union[str, Sequence[str], None] = 'b7f3d2c8a5e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_announcements_created_by_id", "announcements", ["created_by_id"])
    op.create_index("ix_announcements_status_pub", "announcements", ["status", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_announcements_status_pub", table_name="announcements")
    op.drop_index("ix_announcements_created_by_id", table_name="announcements")
    op.drop_table("announcements")
