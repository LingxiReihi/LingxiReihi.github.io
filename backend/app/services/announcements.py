"""更新公告读写。排序口径唯一实现处：先按 status 分组（published 在前、draft 恒垫后，
spec §2——先发布后改回草稿的条目带旧 published_at，不能按时间混进发布组），
组内再按双键：有 published_at 者在前按发布时间倒序、无者垫后，同级按创建时间倒序。
（SQLite 不支持 NULLS LAST，用 (published_at IS NULL) 双键等价。）"""
from sqlalchemy import case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import utcnow
from ..models import Announcement, AnnouncementRead

STATUSES = ("draft", "published")


def to_dict(a: Announcement) -> dict:
    return {
        "id": a.id, "title": a.title, "body_md": a.body_md, "status": a.status,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "created_by": a.created_by.nickname if a.created_by else None,
    }


def _order_keys():
    """published 在前、draft 垫底；组内有 published_at 者按发布时间倒序、无者按创建时间倒序。"""
    published_first = case((Announcement.status == "published", 0), else_=1)
    null_last = case((Announcement.published_at.is_(None), 1), else_=0)
    return [published_first, null_last, Announcement.published_at.desc(), Announcement.created_at.desc()]


def _clamp(limit: int) -> int:
    return max(1, min(limit, 100))


async def list_announcements(db: AsyncSession, limit: int = 20) -> list[Announcement]:
    rows = (await db.execute(
        select(Announcement)
        .order_by(*_order_keys())
        .limit(_clamp(limit)))).scalars().all()
    return list(rows)


async def list_unread(db: AsyncSession, user_id: int, limit: int = 20) -> list[Announcement]:
    # /unread 喂全员登录弹窗：只推 published——草稿是作者自己没写完的备忘（含「发布后又改回
    # 草稿、仍带旧 published_at」的行），不该弹给其他人（spec §3 裁定）。
    rows = (await db.execute(
        select(Announcement).where(
            Announcement.status == "published",
            ~exists().where(
                AnnouncementRead.announcement_id == Announcement.id,
                AnnouncementRead.user_id == user_id))
        .order_by(*_order_keys()).limit(_clamp(limit)))).scalars().all()
    return list(rows)


async def mark_read(db: AsyncSession, user_id: int, ids: list[int]) -> int:
    """幂等 + 容忍脏输入：只接受真实存在的公告 id，已记过的不重复写。"""
    if not ids:
        return 0
    valid = set((await db.execute(
        select(Announcement.id).where(Announcement.id.in_(ids)))).scalars().all())
    if not valid:
        return 0
    have = set((await db.execute(
        select(AnnouncementRead.announcement_id).where(
            AnnouncementRead.user_id == user_id,
            AnnouncementRead.announcement_id.in_(valid)))).scalars().all())
    new = valid - have
    for aid in sorted(new):
        db.add(AnnouncementRead(announcement_id=aid, user_id=user_id))
    if new:
        await db.commit()
    return len(new)


def apply_write(a: Announcement, *, title: str | None = None, body_md: str | None = None,
                status: str | None = None, published_at=None, user_id: int | None = None) -> None:
    """新建与部分更新共用：title/body 传 None 即不动；发布语义见三条注释。"""
    if title is not None:
        a.title = title.strip()
    if body_md is not None:
        a.body_md = body_md
    if published_at is not None:
        a.published_at = published_at
    if status is not None and status != a.status:
        # 置 published 且从无发布时间（或草稿期改过日期又清空）→ 补 now；已有首发时间不动（重发布不覆盖）；
        # 改回 draft 保留 published_at（spec §2）。
        if status == "published" and a.published_at is None:
            a.published_at = utcnow()
        a.status = status
    if user_id is not None and a.created_by_id is None:
        a.created_by_id = user_id
