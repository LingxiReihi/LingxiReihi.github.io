"""mail queue: 出站发信队列 + 评论通知去重列

新表 mail_queue 让所有非敏感发信先入队再按额度/退避冲出（预算与退避都从这张表推导，
重启不失效）；comments.notified_at 用来保证「首次审核通过才通知评论者」，
去重靠这一列而不是靠队列里有没有行，所以「通过→拒绝→再通过」也只发一封。

Revision ID: e2b5d7f9a4c1
Revises: d1f4a6c8b307
Create Date: 2026-10-06 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.db import TZDateTime


# revision identifiers, used by Alembic.
revision: str = 'e2b5d7f9a4c1'
down_revision: Union[str, Sequence[str], None] = 'd1f4a6c8b307'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mail_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('to_addr', sa.String(length=120), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(length=200), nullable=False),
        sa.Column('comment_id', sa.Integer(), nullable=True),
        sa.Column('next_try_at', TZDateTime(), nullable=False),
        sa.Column('created_at', TZDateTime(), nullable=False),
        sa.Column('updated_at', TZDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_mail_queue_status_next', 'mail_queue', ['status', 'next_try_at'])
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notified_at', TZDateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_column('notified_at')
    op.drop_index('ix_mail_queue_status_next', table_name='mail_queue')
    op.drop_table('mail_queue')
