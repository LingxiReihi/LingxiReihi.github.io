"""retire home settings group: 清掉 home.sections 与 home.featured_content_ids

首页改版成「最新 / 热门 / 管理团队」三段后，那四个按类型分的开关和「精选内容 id」都没有
消费者了（/home 已不再算 featured_models，site-config 已不再下发 sections）。留着就是
2026-10-06 绑定审计刚修过的那种「入库但前台无人读」的死配置，所以整组前滚清除。

Revision ID: b7f3d2c8a5e4
Revises: e2b5d7f9a4c1
Create Date: 2026-10-06 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f3d2c8a5e4'
down_revision: Union[str, Sequence[str], None] = 'e2b5d7f9a4c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RETIRED = ("home.sections", "home.featured_content_ids")


def upgrade() -> None:
    conn = op.get_bind()
    for key in RETIRED:
        conn.execute(sa.text("DELETE FROM site_settings WHERE key = :k"), {"k": key})


def downgrade() -> None:
    """退回默认值即可：这两项在被撤掉前对前台的实际渲染已经没有任何影响（新首页不读它们）。"""
    import json

    conn = op.get_bind()
    defaults = {"home.sections": json.dumps(
                    {"hero": True, "posts": True, "models": True, "chats": True}, ensure_ascii=False),
                "home.featured_content_ids": "[]"}
    for key, value in defaults.items():
        conn.execute(sa.text("INSERT INTO site_settings (key, value, updated_at) "
                             "VALUES (:k, :v, CURRENT_TIMESTAMP)"), {"k": key, "v": value})
