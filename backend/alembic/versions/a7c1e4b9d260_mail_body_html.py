"""mail_queue: 增加 body_html 列

公告与评论通知改成「Markdown 渲染成 HTML」发送，纯文本继续留作兜底。
body_html 为空串表示这封信只有纯文本（历史行与口令重置邮件都是这种）。

Revision ID: a7c1e4b9d260
Revises: d3a9c5e7b412
Create Date: 2026-11-01 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c1e4b9d260'
down_revision: Union[str, Sequence[str], None] = 'd3a9c5e7b412'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('mail_queue', sa.Column('body_html', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('mail_queue', 'body_html')
