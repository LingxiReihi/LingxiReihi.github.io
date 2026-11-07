"""管理员账号与授权管理：仅持 admin:manage 者可用（顶级管理员隐式拥有）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx
from ...core.errors import AppException, ErrorCode, ok
from ...core.logs import log_event
from ...schemas.admin import AdminCreate, AdminUpdate, GrantsReq
from ...services import admin_accounts as svc
from ...services import profiles, rebuild

router = APIRouter(prefix="/admins", tags=["admin-accounts"])


def _require_manage(ctx: AdminContext) -> None:
    if not ctx.can("admin:manage"):
        raise AppException(ErrorCode.FORBIDDEN, "你没有管理员账号管理权")


@router.get("")
async def list_admins(db: AsyncSession = Depends(get_db),
                      ctx: AdminContext = Depends(get_admin_ctx)):
    _require_manage(ctx)
    return ok(await svc.list_admins(db))


@router.post("")
async def create_admin(body: AdminCreate, db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    _require_manage(ctx)
    row = await svc.create_admin(
        db, ctx=ctx, username=body.username, password=body.password, email=body.email,
        nickname=body.nickname, note=body.note, role=body.role,
        grants=[g.model_dump() for g in body.grants])
    log_event("admin", f"创建管理员 {row['username']}（role={row['role']}，权限 {len(row['grants'])} 条）",
              actor=ctx.user.username)
    return ok(row)


@router.put("/{admin_id}")
async def update_admin(admin_id: int, body: AdminUpdate, db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    _require_manage(ctx)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise AppException(ErrorCode.BAD_REQUEST, "没有需要变更的字段")
    row = await svc.update_admin(db, ctx=ctx, admin_id=admin_id, fields=fields)
    sensitive = {"is_active", "role", "password"} & set(fields)
    log_event("admin", f"变更管理员 {row['username']}：{sorted(fields)}", actor=ctx.user.username,
              level="warning" if sensitive else "info")
    if ctx.is_super and (profiles.ABOUT_TRIGGER_FIELDS & set(fields)):
        # 在职管理员都在 About 名单上，所以资料与启停变更都要重建这张预渲染页
        rebuild.trigger_rebuild([f"{settings.site_url.rstrip('/')}/about"])
    return ok(row)


@router.put("/{admin_id}/grants")
async def set_grants(admin_id: int, body: GrantsReq, db: AsyncSession = Depends(get_db),
                     ctx: AdminContext = Depends(get_admin_ctx)):
    """覆盖式设权限：传完整集合，服务端整体替换（不做增量语义，避免前后端理解偏差）。"""
    _require_manage(ctx)
    row = await svc.set_grants(db, ctx=ctx, admin_id=admin_id,
                               grants=[g.model_dump() for g in body.grants])
    log_event("admin", f"重设 {row['username']} 权限（{len(row['grants'])} 条）", actor=ctx.user.username)
    return ok(row)


@router.post("/{admin_id}/reset-password")
async def reset_password(admin_id: int, db: AsyncSession = Depends(get_db),
                         ctx: AdminContext = Depends(get_admin_ctx)):
    _require_manage(ctx)
    row, password = await svc.reset_password(db, admin_id=admin_id)
    log_event("admin", f"重置 {row['username']} 口令并强制下线", actor=ctx.user.username, level="warning")
    return ok({**row, "password": password,
               "message": "一次性口令，请立即复制；服务端不保存明文"})


@router.delete("/{admin_id}")
async def delete_admin(admin_id: int, db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    _require_manage(ctx)
    row = await svc.row_dict(db, await svc.get_or_404(db, admin_id))
    await svc.delete_admin(db, actor=ctx.user, admin_id=admin_id)
    log_event("admin", f"删除管理员 {row['username']}", actor=ctx.user.username, level="warning")
    return ok({"deleted": admin_id})
