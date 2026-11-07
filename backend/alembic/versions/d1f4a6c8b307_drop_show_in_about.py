"""about team: 作废 show_in_about —— 名单改为「凡启用的管理员都露出」

上一版（c7d3b9e0a412）加了逐个勾选的露出开关；同日定案推翻：About 名单不再需要开关，
停用即下架。该列从未上线，但已进过本地库，所以按 alembic 只增不减的规矩前滚删列。

Revision ID: d1f4a6c8b307
Revises: c7d3b9e0a412
Create Date: 2026-10-06 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1f4a6c8b307'
down_revision: Union[str, Sequence[str], None] = 'c7d3b9e0a412'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('show_in_about')


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('show_in_about', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    op.get_bind().execute(sa.text("UPDATE users SET show_in_about = 1 WHERE role = 'super'"))
