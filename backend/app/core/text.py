import hashlib
import re
import unicodedata


AVATAR_COUNT = 60  # frontend/public/avatars/00..59.svg，由 frontend/scripts/gen-avatars.mjs 生成


def comment_avatar_url(email: str) -> str:
    """邮箱 md5 → 本地开源图包（DiceBear Open Peeps，设计 CC0）里固定一张。

    不外发明文邮箱；同邮箱永远同一张。图包张数变了会整体重排，改 AVATAR_COUNT 前先想清楚。
    """
    h = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return f"/avatars/{int(h, 16) % AVATAR_COUNT:02d}.svg"


def slugify(text: str, fallback_prefix: str = "c") -> str:
    """ASCII 化 slug；中文等非 ASCII 输入返回 fallback+随机（调用方可改用 id 补齐）。"""
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_ = norm.encode("ascii", "ignore").decode().lower()
    ascii_ = re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")
    if ascii_:
        return ascii_[:180]
    return ""
