"""公开评论接口：先审后显。邮箱仅存库不外发，前台头像取自本地开源图包。"""
import re
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..core.deps import get_page
from ..core.errors import AppException, ErrorCode, ok
from ..models import Comment
from ..services import comment_avatars, comment_notify
from ..services import content as svc

router = APIRouter(prefix="/comments", tags=["comments"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SUBMIT_COOLDOWN_SECONDS = 60
_submit_cooldown: dict[str, float] = {}


class CommentCreate(BaseModel):
    content_id: int
    nickname: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=5, max_length=120)
    body: str = Field(min_length=1, max_length=500)
    website: str = Field("", max_length=200)  # 蜜罐：真人留空

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.match(v.strip()):
            raise ValueError("邮箱格式不正确")
        return v.strip()

    @field_validator("nickname", "body")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


def public_dict(c: Comment, avatars: dict[str, str]) -> dict:
    return {"id": c.id, "nickname": c.nickname, "avatar": comment_avatars.resolve(c.email, avatars),
            "body": c.body, "created_at": c.created_at}


@router.get("")
async def list_comments(content_id: int, pg=Depends(get_page), db: AsyncSession = Depends(get_db)):
    q = select(Comment).where(Comment.content_id == content_id, Comment.status == "approved")
    total = (await db.execute(select(func.count()).select_from(q.order_by(None).subquery()))).scalar_one()
    rows = await db.execute(q.order_by(Comment.id.asc()).offset(pg.offset).limit(pg.page_size))
    avatars = await comment_avatars.load(db)
    return ok({"total": total, "page": pg.page, "page_size": pg.page_size,
               "items": [public_dict(c, avatars) for c in rows.scalars().all()]})


@router.post("")
async def submit_comment(body: CommentCreate, request: Request, background: BackgroundTasks,
                         db: AsyncSession = Depends(get_db)):
    # 蜜罐命中：假装成功，不落库
    if body.website:
        return ok({"pending": True})
    await svc.get_by_id(db, body.content_id)  # 内容须存在且已发布
    now = time.time()
    ip = request.client.host if request.client else "0"
    key = f"{ip}:{body.content_id}"
    if len(_submit_cooldown) > 4096:
        for k, t in list(_submit_cooldown.items()):
            if now - t > SUBMIT_COOLDOWN_SECONDS:
                _submit_cooldown.pop(k, None)
    last = _submit_cooldown.get(key, 0)
    if now - last < SUBMIT_COOLDOWN_SECONDS:
        raise AppException(ErrorCode.RATE_LIMITED, "提交太频繁，请稍后再试")
    _submit_cooldown[key] = now
    c = Comment(content_id=body.content_id, nickname=body.nickname,
                email=body.email, body=body.body, status="pending", submit_ip=ip)
    db.add(c)
    await db.commit()
    # 通知内容作者：响应先返回、发信在后台跑（SMTP 最坏 15s，不该让提交者干等），
    # 且只传 id —— 后台任务自开 session，不借这条请求的会话
    background.add_task(comment_notify.notify, body.content_id, c.id)
    return ok({"pending": True}, message="已提交，通过审核后展示")
