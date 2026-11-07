"""更新公告 CRUD。写侧与列表读侧要 announcement:manage；/unread、/read 降为仅登录
（get_current_admin，不判权限点）——v2 形态是全员登录弹窗，未读水位跟人走。
不接 trigger_rebuild/sitemap：前台无消费者。首次发布另走邮件通知（announcement_notify）。"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx, get_current_admin
from ...core.errors import AppException, ErrorCode, ok
from ...models import Announcement, User
from ...schemas.admin import AnnouncementPatch, AnnouncementReadReq, AnnouncementReq
from ...services import announcement_notify
from ...services import announcements as svc

router = APIRouter(prefix="/announcements", tags=["admin-announcements"])


def _notify_first_publish(background: BackgroundTasks, a: Announcement, *, was_published: bool) -> None:
    """首次发布（现在 published 且进来之前不是）才排通知。

    只挂后台任务、不在请求事务里做任何发信相关写操作：公告此刻已 commit，通知失败牵连不到它，
    保存响应也不必等 SMTP。
    """
    if a.status == "published" and not was_published:
        background.add_task(announcement_notify.notify_published, a.id)


async def _get(db: AsyncSession, announcement_id: int) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if not a:
        raise AppException(ErrorCode.NOT_FOUND, "公告不存在")
    return a


@router.get("")
async def list_announcements(limit: int = 20, db: AsyncSession = Depends(get_db),
                             ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    rows = await svc.list_announcements(db, limit)
    return ok({"items": [svc.to_dict(a) for a in rows]})


@router.post("")
async def create_announcement(body: AnnouncementReq, background: BackgroundTasks,
                              db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    a = Announcement(title=body.title.strip(), body_md=body.body_md, status=body.status,
                     published_at=body.published_at, created_by_id=ctx.user.id)
    if a.status == "published" and a.published_at is None:
        from ...core.db import utcnow
        a.published_at = utcnow()
    db.add(a)
    await db.commit()
    await db.refresh(a)
    data = svc.to_dict(a)                        # 先出快照：通知走后台任务，不参与本请求
    _notify_first_publish(background, a, was_published=False)
    return ok(data)


@router.get("/unread")
async def unread_announcements(limit: int = 20, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_admin)):
    """登录弹窗用：当前管理员未读的公告。读全员开放，不判 announcement:manage。"""
    rows = await svc.list_unread(db, user.id, limit)
    return ok({"items": [svc.to_dict(a) for a in rows]})


@router.post("/read")
async def mark_announcements_read(body: AnnouncementReadReq, db: AsyncSession = Depends(get_db),
                                  user: User = Depends(get_current_admin)):
    """把这批 id 记为该用户已读。弹窗关闭即整批上报，幂等、脏 id 静默跳过。"""
    marked = await svc.mark_read(db, user.id, body.ids)
    return ok({"marked": marked})


@router.put("/{announcement_id}")
async def update_announcement(announcement_id: int, body: AnnouncementPatch,
                              background: BackgroundTasks,
                              db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    a = await _get(db, announcement_id)
    was_published = a.status == "published"          # 先记下，apply_write 会就地改状态
    svc.apply_write(a, **body.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(a)
    data = svc.to_dict(a)                        # 同上：快照先于通知旁路
    _notify_first_publish(background, a, was_published=was_published)
    return ok(data)


@router.delete("/{announcement_id}")
async def delete_announcement(announcement_id: int, db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    a = await _get(db, announcement_id)
    await db.delete(a)
    await db.commit()
    return ok({"deleted": announcement_id})
