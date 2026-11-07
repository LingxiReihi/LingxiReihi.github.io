"""评论头像：邮箱对上某个管理员 → 用他个人资料里的头像；否则回落本地开源图包。

评论邮箱是自报未验证的，所以任何人知道管理员邮箱就能拿到那张头像 —— 冒充面靠
先审后显人工把关（审核页看得到 email 与提交 IP），这是 2026-10-06 拍定的口径。
不查 is_active：头像不是权限，且停用账号的历史评论不该突然变脸。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.text import comment_avatar_url
from ..models import User


def normalize(email: str | None) -> str:
    return (email or "").strip().lower()


async def load(db: AsyncSession) -> dict[str, str]:
    """归一化邮箱 → 管理员头像；没填邮箱或没上传头像的账号不进表。"""
    rows = await db.execute(select(User.email, User.avatar_url))
    return {normalize(e): a for e, a in rows.all() if e and a}


def resolve(email: str, avatars: dict[str, str]) -> str:
    return avatars.get(normalize(email)) or comment_avatar_url(email)
