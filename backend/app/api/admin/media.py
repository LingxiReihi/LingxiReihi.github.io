"""素材管理（Flow F-3）。素材库全站可见可复用，归属只约束删除权。

整理动作（改分类、重命名）只改数据库字段：`storage_key` 是素材的永久地址，
落盘后不再变动，所以已有正文链接、封面引用、外部分享都不会因为整理而失效。
"""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx, get_page
from ...core.errors import AppException, ErrorCode, ok
from ...core.logs import log_event
from ...models import MediaAsset, User
from ...services.media import (
    CATEGORIES, asset_public, assert_deletable, media_usage, referencing_contents,
    rename_asset, set_category, store_upload,
)

router = APIRouter(prefix="/media", tags=["admin-media"])


class CategorizeReq(BaseModel):
    ids: list[int]
    category: str


class RenameReq(BaseModel):
    filename: str


def _admin_dict(a: MediaAsset, ctx: AdminContext) -> dict:
    if ctx.is_super:
        can_delete = True
    elif a.uploaded_by_id is None or a.uploaded_by_id != ctx.user.id:
        can_delete = False       # 他人上传或无主素材：仅顶级管理员可删
    else:
        can_delete = ctx.can("media:delete")
    return {**asset_public(a),
            "uploader_id": a.uploaded_by_id,
            "uploader_nickname": (a.uploaded_by.nickname if a.uploaded_by else None),
            "can_delete": can_delete}


@router.post("")
async def upload(file: UploadFile = File(...), category: str = Form("blog"),
                 db: AsyncSession = Depends(get_db),
                 ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("media:write", subject="素材上传")
    data = await file.read()
    asset = await store_upload(db, file.filename or "unnamed", file.content_type or "", data, category)
    asset.uploaded_by_id = ctx.user.id
    await db.commit()
    log_event("upload", f"上传素材 {asset.storage_key} ({asset.size}B, 分类={category})",
              actor=ctx.user.username)
    return ok(_admin_dict(asset, ctx))


@router.post("/categorize")
async def categorize(body: CategorizeReq, db: AsyncSession = Depends(get_db),
                     ctx: AdminContext = Depends(get_admin_ctx)):
    """批量改分类标签。**不移动文件、不改写 URL** —— 分类只是整理视角。"""
    ctx.need("media:write", subject="素材归类")
    if not body.ids:
        raise AppException(ErrorCode.BAD_REQUEST, "未选择素材")
    if body.category not in CATEGORIES:
        raise AppException(ErrorCode.BAD_REQUEST, f"未知分类 {body.category}")
    rows = await db.execute(select(MediaAsset).where(MediaAsset.id.in_(body.ids)))
    by_id = {a.id: a for a in rows.scalars().all()}
    # 改分类会写库，按归属隔离（与删除同一条规则）
    allowed, denied = [], []
    for i in body.ids:
        a = by_id.get(i)
        if a is not None and (ctx.is_super or a.uploaded_by_id == ctx.user.id):
            allowed.append(a)
        else:
            denied.append(i)
    updated = await set_category(db, allowed, body.category)
    log_event("media", f"批量改分类 ids={body.ids} → {body.category}（更新 {updated}，无权 {len(denied)}）",
              actor=ctx.user.username)
    return ok({"updated": updated, "denied": denied})


@router.get("/contents")
async def list_media_contents(db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    """右下拉数据：引用过素材的内容（按引用条数排序）＋「未被引用」计数。

    分类是自动的：正文里的 /media 链接、封面、模型附件三处都算引用，
    所以文章改了正文，这里的分组会跟着变，不需要手工维护。
    """
    usage = await media_usage(db)
    counts: dict[int, int] = {}
    briefs: dict[int, dict] = {}
    for cs in usage.values():
        for c in cs:
            counts[c["id"]] = counts.get(c["id"], 0) + 1
            briefs[c["id"]] = c
    total = (await db.execute(select(func.count()).select_from(MediaAsset))).scalar_one()
    items = [{"id": cid, "title": briefs[cid]["title"], "type": briefs[cid]["type"],
              "slug": briefs[cid]["slug"], "count": n}
             for cid, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ok({"items": items, "unused": max(0, total - len(usage)), "total": total})


@router.get("")
async def list_media(kind: str | None = None, q: str | None = None, category: str | None = None,
                     mine: str | None = None, content_id: int | None = None,
                     unused: str | None = None,
                     pg=Depends(get_page), db: AsyncSession = Depends(get_db),
                     ctx: AdminContext = Depends(get_admin_ctx)):
    stmt = select(MediaAsset)
    if kind:
        stmt = stmt.where(MediaAsset.kind == kind)
    if category:
        if category == "none":
            stmt = stmt.where(MediaAsset.category.is_(None))
        else:
            stmt = stmt.where(MediaAsset.category == category)
    if q:
        stmt = stmt.where(MediaAsset.filename.contains(q))
    if mine and mine.lower() in ("1", "true", "yes"):
        stmt = stmt.where(MediaAsset.uploaded_by_id == ctx.user.id)

    # 引用关系每次现算：内容量小，一次全表扫比逐条查三张表划算，也不会出现缓存不一致
    usage = await media_usage(db)
    if unused and unused.lower() in ("1", "true", "yes"):
        if usage:
            stmt = stmt.where(MediaAsset.id.not_in(list(usage)))
    elif content_id is not None:
        hit = [aid for aid, cs in usage.items() if any(c["id"] == content_id for c in cs)]
        if not hit:
            return ok({"total": 0, "page": pg.page, "page_size": pg.page_size, "items": []})
        stmt = stmt.where(MediaAsset.id.in_(hit))

    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = await db.execute(stmt.order_by(MediaAsset.id.desc()).offset(pg.offset).limit(pg.page_size))
    return ok({"total": total, "page": pg.page, "page_size": pg.page_size,
               "items": [{**_admin_dict(a, ctx), "used_by": usage.get(a.id, [])}
                         for a in rows.scalars().all()]})


@router.patch("/{asset_id}")
async def rename_media(asset_id: int, body: RenameReq, db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    """重命名素材：只改展示名，`storage_key`/URL 保持不变。"""
    ctx.need("media:write", subject="素材重命名")
    a = await db.get(MediaAsset, asset_id)
    if not a:
        raise AppException(ErrorCode.NOT_FOUND, "素材不存在")
    ctx.need_owner(a.uploaded_by_id, owner_name=(a.uploaded_by.nickname if a.uploaded_by else None),
                   subject="该素材")
    old = a.filename
    a = await rename_asset(db, a, body.filename)
    log_event("media", f"重命名素材 id={asset_id} {old} → {a.filename}（URL 不变）",
              actor=ctx.user.username)
    return ok(_admin_dict(a, ctx))


@router.delete("/{asset_id}")
async def delete_media(asset_id: int, db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("media:delete", subject="素材删除")
    a = await db.get(MediaAsset, asset_id)
    if not a:
        raise AppException(ErrorCode.NOT_FOUND, "素材不存在")
    ctx.need_owner(a.uploaded_by_id, owner_name=(a.uploaded_by.nickname if a.uploaded_by else None),
                   subject="该素材")
    await assert_deletable(db, a)
    # v1 只删记录不删磁盘文件（防误删共享字节；孤儿清理由运维脚本负责）
    await db.delete(a)
    await db.commit()
    log_event("media", f"删除素材 id={asset_id} {a.storage_key}", actor=ctx.user.username)
    return ok({"deleted": asset_id})
