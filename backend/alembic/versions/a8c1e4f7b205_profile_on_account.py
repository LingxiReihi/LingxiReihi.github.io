"""profile on account: 资料从 site_settings.profile 迁到管理员账号行

Revision ID: a8c1e4f7b205
Revises: f4a8c2d6e9b3
Create Date: 2026-10-04 01:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8c1e4f7b205'
down_revision: Union[str, Sequence[str], None] = 'f4a8c2d6e9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUPER_ID = "(SELECT id FROM users WHERE role='super' ORDER BY id LIMIT 1)"

# site_settings 里的旧 profile 键 → users 表目标列（JSON 列直接搬值）
MOVES = [
    ("profile.nickname", "nickname", "nickname"),
    ("profile.avatar", "avatar_url", "str"),
    ("profile.signature", "signature", "str"),
    ("profile.bio_md", "bio_md", "str"),
    ("profile.social_links", "social_links", "json"),
    ("profile.skills", "skills", "json"),
    ("profile.experience", "experience", "json"),
]


def _empty_where(column: str, kind: str) -> str:
    """只在目标列还没被特意设过时才写入，避免覆盖账号自己的编辑。"""
    if kind == "nickname":
        # 账号昵称等于登录名或为空 → 视为没设过，可被站点旧昵称接管
        return f"({column} IS NULL OR {column} = '' OR {column} = username)"
    if kind == "json":
        return f"{column} IS NULL"
    return f"({column} IS NULL OR {column} = '')"


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('signature', sa.String(length=200), nullable=False,
                                      server_default=''))
        batch_op.add_column(sa.Column('bio_md', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('social_links', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('skills', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('experience', sa.JSON(), nullable=True))

    # 一次性搬迁：全局 profile 的值 → super 那一行；JSON 列以 JSON 文本写入。
    # 库里没有 super 时子查询为空，整段自然空转，不会误写其他账号。
    import json

    conn = op.get_bind()
    moved = 0
    for key, column, kind in MOVES:
        row = conn.execute(sa.text("SELECT value FROM site_settings WHERE key = :k"),
                           {"k": key}).first()
        if not row or row[0] is None:
            continue
        try:
            value = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if kind == "json":
            if not value:
                continue        # 空列表没必要占位
            payload = json.dumps(value, ensure_ascii=False)
        else:
            payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            if not payload:
                continue
        conn.execute(sa.text(f"UPDATE users SET {column} = :v WHERE id = {SUPER_ID} "
                             f"AND {_empty_where(column, kind)}"), {"v": payload})
        moved += 1
    conn.execute(sa.text("DELETE FROM site_settings WHERE key LIKE 'profile.%'"))
    print(f"[a8c1e4f7b205] profile → super 账号：搬移 {moved} 项，site_settings.profile.* 已清除")


def downgrade() -> None:
    """资料退回全局 profile 组（只回填 super 那一份；其余账号的资料在旧模型里没有落点）。"""
    import json

    conn = op.get_bind()
    for column, key, kind in [("nickname", "profile.nickname", "str"),
                              ("avatar_url", "profile.avatar", "str"),
                              ("signature", "profile.signature", "str"),
                              ("bio_md", "profile.bio_md", "str"),
                              ("social_links", "profile.social_links", "json"),
                              ("skills", "profile.skills", "json"),
                              ("experience", "profile.experience", "json")]:
        row = conn.execute(sa.text(
            f"SELECT {column} FROM users WHERE role='super' ORDER BY id LIMIT 1")).first()
        if not row or row[0] is None or row[0] == "":
            continue
        # users 的 JSON 列里存的已是合法 JSON 文本，原样写回；文本列才需要加一层引号
        payload = str(row[0]) if kind == "json" else json.dumps(str(row[0]), ensure_ascii=False)
        conn.execute(sa.text(
            "INSERT INTO site_settings (key, value, updated_at) "
            "VALUES (:k, :v, datetime('now')) ON CONFLICT(key) DO NOTHING"),
            {"k": key, "v": payload})
    with op.batch_alter_table('users', schema=None) as batch_op:
        for col in ('experience', 'skills', 'social_links', 'bio_md', 'signature'):
            batch_op.drop_column(col)
