"""「我的资料」：每位管理员改自己那份，不需要任何权限点（2026-10 定案）。

站点级 site_settings.profile 组已废：About/首页/内容页署名都从账号行读。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx
from ...core.errors import AppException, ErrorCode, ok
from ...core.logs import log_event
from ...schemas.admin import ProfileReq
from ...services import profiles
from ...services import rebuild

router = APIRouter(prefix="/profile", tags=["admin-profile"])


@router.get("")
async def my_profile(ctx: AdminContext = Depends(get_admin_ctx)):
    """自己那份 + 可改字段清单（每位管理员一样，改不了别人的）。"""
    d = profiles.self_view(ctx.user)
    d["editable"] = list(profiles.EDITABLE_FIELDS)
    d["is_super"] = ctx.is_super
    return ok(d)


@router.put("")
async def update_my_profile(body: ProfileReq, ctx: AdminContext = Depends(get_admin_ctx),
                            db: AsyncSession = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise AppException(ErrorCode.BAD_REQUEST, "没有需要变更的字段")
    try:
        view = await profiles.update_profile(db, ctx.user, fields)
    except ValueError as e:
        raise AppException(ErrorCode.FORBIDDEN, str(e))
    log_event("admin", f"更新自己的资料：{sorted(fields)}", actor=ctx.user.username)
    if profiles.about_visible(ctx.user) and (profiles.ABOUT_FIELDS & set(fields)):
        # About 是预渲染的：在职管理员都会上页，改了影响上页的字段就入队重建
        rebuild.trigger_rebuild([f"{settings.site_url.rstrip('/')}/about"])
    view["editable"] = list(profiles.EDITABLE_FIELDS)
    view["is_super"] = ctx.is_super
    return ok(view)
