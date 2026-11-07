"""后台评论审核：列表（含邮箱）、批量通过/拒绝、删除。"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx, get_current_admin, get_page
from ...core.errors import AppException, ErrorCode, ok
from ...core.logs import log_event
from ...models import Comment, Content, User
from ...services import comment_avatars, comment_notify, mail_queue

router = APIRouter(prefix="/comments", tags=["admin-comments"])

MODERATE_STATUSES = ("pending", "approved", "rejected")


class ModerateReq(BaseModel):
    ids: list[int]
    status: str


def _admin_dict(c: Comment, title: str | None, avatars: dict[str, str]) -> dict:
    return {"id": c.id, "content_id": c.content_id, "content_title": title,
            "nickname": c.nickname, "email": c.email,
            "avatar": comment_avatars.resolve(c.email, avatars), "body": c.body, "status": c.status,
            "submit_ip": c.submit_ip, "created_at": c.created_at, "reviewed_at": c.reviewed_at}


@router.get("")
async def list_comments(status: str | None = None, content_id: int | None = None,
                        pg=Depends(get_page), db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_admin)):
    stmt = select(Comment, Content.title).join(Content, Content.id == Comment.content_id, isouter=True)
    cond = []
    if status:
        cond.append(Comment.status == status)
    if content_id:
        cond.append(Comment.content_id == content_id)
    if cond:
        stmt = stmt.where(*cond)
    total = (await db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = await db.execute(stmt.order_by(Comment.id.desc()).offset(pg.offset).limit(pg.page_size))
    pairs = rows.all()
    pending = (await db.execute(
        select(func.count()).select_from(Comment).where(Comment.status == "pending"))).scalar_one()
    avatars = await comment_avatars.load(db)
    return ok({"total": total, "page": pg.page, "page_size": pg.page_size, "pending": pending,
               "items": [_admin_dict(c, t, avatars) for c, t in pairs]})


@router.post("/moderate")
async def moderate(body: ModerateReq, background: BackgroundTasks,
                   db: AsyncSession = Depends(get_db),
                   ctx: AdminContext = Depends(get_admin_ctx)):
    # 待审队列是站点级卫生工作，全站共享、不按内容归属过滤（唯一的归属隔离例外，见 spec §5）
    ctx.need("comment:moderate", subject="评论审核")
    if not body.ids or body.status not in MODERATE_STATUSES:
        raise AppException(ErrorCode.BAD_REQUEST, "参数无效")
    rows = await db.execute(select(Comment).where(Comment.id.in_(body.ids)))
    now = datetime.now(timezone.utc)
    n = notified = 0
    for c in rows.scalars():
        c.status, c.reviewed_at = body.status, now
        c.reviewed_by_id = ctx.user.id
        n += 1
        if body.status == "approved":
            content = await db.get(Content, c.content_id)
            if content is not None and await comment_notify.queue_visitor_notice(db, c, content):
                notified += 1
    await db.commit()
    if notified:
        background.add_task(mail_queue.drain_now)   # 审核响应不等 SMTP，出信在后台跑
    log_event("comment", f"审核评论 ids={body.ids} → {body.status}（{n} 条，通知评论者 {notified} 封）",
              actor=ctx.user.username)
    return ok({"updated": n, "notified": notified})


@router.delete("/{comment_id}")
async def delete_comment(comment_id: int, db: AsyncSession = Depends(get_db),
                         ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("comment:moderate", subject="评论删除")
    c = await db.get(Comment, comment_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "评论不存在")
    await db.delete(c)
    await db.commit()
    log_event("comment", f"删除评论 id={comment_id}", actor=ctx.user.username)
    return ok({"deleted": comment_id})
