"""后台内容管理（Flow F）：docs/api-reference.md §5。"""
import secrets

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.public import make_preview_token
from ...core.config import settings
from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx, get_page
from ...core.errors import AppException, ErrorCode, ok
from ...core.logs import log_event
from ...core.text import slugify
from ...models import Content, MediaAsset, Tag, content_media, content_tags
from ...schemas.admin import ContentPatch, ContentUpsert, StatusReq, TagRef
from ...services import image_import, rebuild, sitemap
from ...services.media import asset_public

router = APIRouter(prefix="/contents", tags=["admin-contents"])

_TYPE_PATH = {"article": "blog", "model": "models", "chat": "chats"}


def public_path(c: Content, base: str) -> str:
    if c.type == "chat":
        return f"{base}/chats/{c.id}"
    return f"{base}/{_TYPE_PATH[c.type]}/{c.slug}"


async def _resolve_tags(db: AsyncSession, refs: list[TagRef], type_: str) -> list[Tag]:
    """标签按内容类型隔离：id 必须属于该类型；name 只在本类型内查找，查不到即新建。"""
    tags = []
    for r in refs:
        t = None
        if r.id:
            t = await db.get(Tag, r.id)
            if not t:
                raise AppException(ErrorCode.BAD_REQUEST, f"标签 id={r.id} 不存在")
            if t.type != type_:
                raise AppException(ErrorCode.BAD_REQUEST, f"标签「{t.name}」属于{t.type}，不能用于{type_}内容")
        elif r.name:
            t = (await db.execute(select(Tag).where(Tag.name == r.name, Tag.type == type_))).scalar_one_or_none()
            if not t:
                t = Tag(name=r.name, slug=slugify(r.name) or f"t-{secrets.token_hex(3)}", type=type_)
                db.add(t)
                await db.flush()
        else:
            raise AppException(ErrorCode.BAD_REQUEST, "标签需含 id 或 name")
        tags.append(t)
    return tags


def _asset_admin_dict(c: Content, ctx: AdminContext) -> dict:
    return {
        "id": c.id, "type": c.type, "status": c.status, "title": c.title, "slug": c.slug,
        "summary": c.summary, "cover_asset_id": c.cover_asset_id,
        "cover": (f"/media/{c.cover_asset.storage_key}" if c.cover_asset else None),
        "media_kind": c.media_kind, "extra": c.extra or {},
        "tags": [{"id": t.id, "name": t.name, "slug": t.slug, "type": t.type} for t in c.tags],
        "column_id": c.column_id,
        "column": ({"id": c.column.id, "name": c.column.name, "slug": c.column.slug, "type": c.column.type}
                   if c.column else None),
        "published_at": c.published_at, "created_at": c.created_at, "updated_at": c.updated_at,
        "view_count": c.view_count, "likes": c.likes,
        "owner_id": c.created_by_id,
        "owner_nickname": (c.created_by.nickname if c.created_by else None),
        "can_edit": ctx.can_edit_content(c),
        "can_delete": ctx.can_edit_content(c, need_delete=True),
        "denied_reason": ctx.content_denied_reason(c),
    }


async def _check_column(db: AsyncSession, column_id: int | None, type_: str):
    """校验栏目存在且类型匹配，返回 (id, 名称)。"""
    if column_id is None:
        return None, None
    from ...models import Column
    col = await db.get(Column, column_id)
    if not col:
        raise AppException(ErrorCode.BAD_REQUEST, f"栏目 id={column_id} 不存在")
    if col.type != type_:
        raise AppException(ErrorCode.BAD_REQUEST, f"栏目「{col.name}」属于{col.type}，不能用于{type_}内容")
    return col.id, col.name


async def _validate_assets(db: AsyncSession, ids: list[int]) -> list[MediaAsset]:
    if not ids:
        return []
    rows = (await db.execute(select(MediaAsset).where(MediaAsset.id.in_(ids)))).scalars().all()
    found = {a.id for a in rows}
    missing = set(ids) - found
    if missing:
        raise AppException(ErrorCode.BAD_REQUEST, f"素材不存在: {sorted(missing)}")
    by_id = {a.id: a for a in rows}
    return [by_id[i] for i in ids]


@router.get("")
async def list_contents(type: str | None = None, status: str | None = None,
                        q: str | None = None, tag: str | None = None,
                        column: str | None = None, mine: str | None = None,
                        pg=Depends(get_page), db: AsyncSession = Depends(get_db),
                        ctx: AdminContext = Depends(get_admin_ctx)):
    stmt = select(Content)
    cond = []
    if type:
        cond.append(Content.type == type)
    if status:
        cond.append(Content.status == status)
    if mine and mine.lower() in ("1", "true", "yes"):
        cond.append(Content.created_by_id == ctx.user.id)
    if q:
        cond.append(or_(Content.title.contains(q), Content.summary.contains(q)))
    if tag:
        cond.append(Content.id.in_(
            select(content_tags.c.content_id).join(Tag, Tag.id == content_tags.c.tag_id)
            .where(or_(Tag.slug == tag, Tag.name == tag))))
    if column:
        from ...models import Column
        colq = select(Column.id).where(or_(Column.slug == column, Column.name == column))
        if type:
            colq = colq.where(Column.type == type)
        cond.append(Content.column_id.in_(colq))
    if cond:
        stmt = stmt.where(*cond)
    total = (await db.execute(select(func.count()).select_from(
        stmt.order_by(None).subquery()))).scalar_one()
    rows = await db.execute(stmt.order_by(Content.updated_at.desc(), Content.id.desc())
                            .offset(pg.offset).limit(pg.page_size))
    items = rows.scalars().all()
    from ...models import Comment
    counts: dict[int, int] = {}
    if items:
        crows = await db.execute(
            select(Comment.content_id, func.count()).where(
                Comment.content_id.in_([c.id for c in items])).group_by(Comment.content_id))
        counts = dict(crows.all())
    return ok({"total": total, "page": pg.page, "page_size": pg.page_size,
               "items": [{**_asset_admin_dict(c, ctx), "comment_count": counts.get(c.id, 0)}
                         for c in items]})


async def _unique_slug(db: AsyncSession, type_: str, slug: str | None, title: str,
                       exclude_id: int | None = None) -> str:
    if type_ == "chat":
        return ""
    s = slug or slugify(title) or f"{_TYPE_PATH[type_][:4]}-{secrets.token_hex(3)}"
    q = select(Content.id).where(Content.slug == s)
    if exclude_id:
        q = q.where(Content.id != exclude_id)
    if (await db.execute(q.limit(1))).first():
        raise AppException(ErrorCode.CONFLICT, "slug 已存在", data={"field": "slug"})
    return s


@router.post("")
async def create_content(body: ContentUpsert, db: AsyncSession = Depends(get_db),
                         ctx: AdminContext = Depends(get_admin_ctx)):
    column_id, column_name = await _check_column(db, body.column_id, body.type)
    ctx.need_scoped("content:write", column_id=column_id, column_name=column_name)
    tags = await _resolve_tags(db, body.tags, body.type)
    assets = await _validate_assets(db, body.asset_ids)
    slug = await _unique_slug(db, body.type, body.slug, body.title)
    from datetime import datetime, timezone
    c = Content(type=body.type, status=body.status, title=body.title, slug=slug or None,
                summary=body.summary, body_md=body.body_md, cover_asset_id=body.cover_asset_id,
                media_kind=body.media_kind, extra=body.extra, tags=tags, assets=assets,
                column_id=column_id, created_by_id=ctx.user.id)
    if body.status == "published":
        c.published_at = datetime.now(timezone.utc)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    pipeline = await _after_publish(db, c)
    log_event("content", f"创建内容 id={c.id} [{c.type}]《{c.title}》状态={c.status}",
              actor=ctx.user.username)
    return ok({**_asset_admin_dict(c, ctx), "pipeline": pipeline})


@router.post("/column-bulk")
async def column_bulk(body: dict, db: AsyncSession = Depends(get_db),
                      ctx: AdminContext = Depends(get_admin_ctx)):
    """批量把内容挂到某栏目（column_id=null 移出）。类型不符或无权变更的逐条跳过并回报。"""
    from ...models import Column
    ids = [int(i) for i in body.get("ids", [])]
    column_id = body.get("column_id")
    if not ids:
        raise AppException(ErrorCode.BAD_REQUEST, "未选择内容")
    col = None
    if column_id is not None:
        col = await db.get(Column, int(column_id))
        if not col:
            raise AppException(ErrorCode.BAD_REQUEST, "栏目不存在")
    rows = (await db.execute(select(Content).where(Content.id.in_(ids)))).scalars().all()
    updated, skipped, denied = 0, 0, []
    dest_column_id = col.id if col else None
    for c in rows:
        if col and c.type != col.type:
            skipped += 1
            continue
        # 起点（当前栏目）与终点（目标栏目）都要过作用域，避免批量路径开后门
        if not ctx.can_edit_content(c) or not ctx.can("content:write", column_id=dest_column_id):
            denied.append(c.id)
            continue
        c.column_id = dest_column_id
        updated += 1
    await db.commit()
    log_event("content",
              f"批量挂栏目 → {col.name if col else '移出'}（更新 {updated}，类型跳过 {skipped}，"
              f"无权 {len(denied)}）", actor=ctx.user.username)
    return ok({"updated": updated, "skipped": skipped, "denied": denied})


@router.get("/{content_id}")
async def get_content(content_id: int, db: AsyncSession = Depends(get_db),
                      ctx: AdminContext = Depends(get_admin_ctx)):
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    d = _asset_admin_dict(c, ctx)
    d["body_md"] = c.body_md
    d["assets"] = [asset_public(a) for a in c.assets]
    return ok(d)


@router.put("/{content_id}")
async def update_content(content_id: int, body: ContentPatch,
                         db: AsyncSession = Depends(get_db),
                         ctx: AdminContext = Depends(get_admin_ctx)):
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    ctx.need_owner(c.created_by_id, owner_name=(c.created_by.nickname if c.created_by else None))
    data = body.model_dump(exclude_unset=True)
    new_column_id, new_column_name = c.column_id, None
    if "column_id" in data:
        new_column_id, new_column_name = await _check_column(db, data["column_id"], c.type)
    # 原地改与搬家都要过作用域：起点或终点任一不在授权栏目内即拒
    ctx.need_scoped("content:write", column_id=c.column_id)
    ctx.need_scoped("content:write", column_id=new_column_id, column_name=new_column_name)
    if "tags" in data and data["tags"] is not None:
        c.tags = await _resolve_tags(db, [TagRef(**t) for t in data.pop("tags")], c.type)
    if "asset_ids" in data and data["asset_ids"] is not None:
        c.assets = await _validate_assets(db, data.pop("asset_ids"))
    if "column_id" in data:
        data["column_id"] = new_column_id
    was_published = c.status == "published"
    new_slug = data.pop("slug", None)
    for k, v in data.items():
        setattr(c, k, v)
    # slug 发布后不可变（收录稳定性）；未编辑过的存量草稿允许补改
    if not was_published and new_slug is not None and new_slug != c.slug:
        c.slug = await _unique_slug(db, c.type, new_slug, c.title or "", exclude_id=c.id) or None
    pipeline = None
    if (not was_published) and c.status == "published":
        from datetime import datetime, timezone
        c.published_at = c.published_at or datetime.now(timezone.utc)
        if c.type != "chat" and not c.slug:
            c.slug = await _unique_slug(db, c.type, None, c.title, exclude_id=c.id)
        pipeline = await _after_publish(db, c)
    await db.commit()
    await db.refresh(c)
    sitemap.invalidate()
    action = "发布" if (not was_published and c.status == "published") else f"更新（状态={c.status}）"
    log_event("content", f"{action}内容 id={c.id}《{c.title}》", actor=ctx.user.username)
    return ok({**_asset_admin_dict(c, ctx), "pipeline": pipeline})


@router.patch("/{content_id}/status")
async def patch_status(content_id: int, body: StatusReq,
                       db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    from datetime import datetime, timezone
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    ctx.need_owner(c.created_by_id, owner_name=(c.created_by.nickname if c.created_by else None))
    ctx.need_scoped("content:write", column_id=c.column_id)
    c.status = body.status
    if body.status == "published" and not c.published_at:
        c.published_at = datetime.now(timezone.utc)
    pipeline = await _after_publish(db, c) if body.status == "published" else None
    await db.commit()
    sitemap.invalidate()
    log_event("content", f"状态变更 id={c.id}《{c.title}》→ {body.status}", actor=ctx.user.username)
    return ok({"id": c.id, "status": c.status, "pipeline": pipeline})


@router.post("/{content_id}/reset-likes")
async def reset_likes(content_id: int, db: AsyncSession = Depends(get_db),
                      ctx: AdminContext = Depends(get_admin_ctx)):
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    ctx.need_owner(c.created_by_id, owner_name=(c.created_by.nickname if c.created_by else None))
    ctx.need_scoped("content:write", column_id=c.column_id)
    c.likes = 0
    await db.commit()
    return ok({"id": c.id, "likes": 0})


@router.delete("/{content_id}")
async def delete_content(content_id: int, db: AsyncSession = Depends(get_db),
                         ctx: AdminContext = Depends(get_admin_ctx)):
    from sqlalchemy import delete as sql_delete

    from ...models import StatsContent, ViewEvent
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    ctx.need_owner(c.created_by_id, owner_name=(c.created_by.nickname if c.created_by else None))
    ctx.need_scoped("content:delete", column_id=c.column_id, subject="内容删除")
    # 清理分析外键依赖后再删（content_tags/content_media 已表级 CASCADE）
    await db.execute(sql_delete(ViewEvent).where(ViewEvent.content_id == content_id))
    await db.execute(sql_delete(StatsContent).where(StatsContent.content_id == content_id))
    await db.delete(c)
    await db.commit()
    sitemap.invalidate()
    log_event("content", f"删除内容 id={content_id}《{c.title}》", actor=ctx.user.username,
              level="warning")
    return ok({"deleted": content_id})


@router.get("/{content_id}/dashboard")
async def content_dashboard(content_id: int, db: AsyncSession = Depends(get_db),
                            ctx: AdminContext = Depends(get_admin_ctx)):
    from ...models import Comment
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    rows = await db.execute(
        select(Comment.status, func.count()).where(Comment.content_id == content_id)
        .group_by(Comment.status))
    counts = dict(rows.all())
    d = _asset_admin_dict(c, ctx)
    d["body_md"] = c.body_md
    d["comments"] = {
        "pending": counts.get("pending", 0), "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "total": sum(counts.values()),
    }
    return ok(d)


@router.post("/{content_id}/preview-token")
async def preview_token(content_id: int, db: AsyncSession = Depends(get_db),
                        _: AdminContext = Depends(get_admin_ctx)):
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    return ok({"token": make_preview_token(c.id), "expires_minutes": 15})


class ImportImagesReq(BaseModel):
    # 传编辑器里的当前正文（可能尚未保存）；不传则用服务端已存的版本
    body_md: str | None = None


def _site_base(request: Request) -> str:
    """回写用的站点前缀。

    以配置的对外地址为准（SITE_URL）：它才是导出后图片该指向的域名，也不受反向代理
    改写 Host 的影响（dev 代理会把 Host 改成后端自己的 127.0.0.1:8001，不能拿来用）。
    只有 SITE_URL 为空这种异常配置才退回请求自身 origin。
    """
    base = (settings.site_url or "").strip().rstrip("/")
    return base or str(request.base_url).rstrip("/")


@router.post("/{content_id}/import-images")
async def import_images(content_id: int, body: ImportImagesReq, request: Request,
                        db: AsyncSession = Depends(get_db),
                        ctx: AdminContext = Depends(get_admin_ctx)):
    """把正文中的外链图片下载进素材库，返回改写后的 Markdown（不自动保存）。

    命名 `{slug}-{图片名}`；回写为 `{站点地址}/media/…` 绝对地址（导出到站外仍可访问）。
    站内 /media（相对或本站绝对）、相对路径、data: 一律跳过。
    """
    c = await db.get(Content, content_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    ctx.need_owner(c.created_by_id, owner_name=(c.created_by.nickname if c.created_by else None))
    ctx.need_scoped("content:write", column_id=c.column_id)
    md = c.body_md if body.body_md is None else body.body_md
    result = await image_import.import_markdown_images(db, c, md, base_url=_site_base(request))
    if result["imported"] or result["failed"]:
        log_event("media",
                  f"内容 id={c.id}《{c.title}》外链图片入库：成功 {len(result['imported'])}，"
                  f"失败 {len(result['failed'])}", actor=ctx.user.username)
    return ok(result)


async def _after_publish(db: AsyncSession, c: Content) -> dict | None:
    """发布钩子：触发本机重建 + 条件推送（异步窗口合并）。"""
    from ...core.config import settings
    if c.status != "published" or c.type == "chat":
        # 杂谈详情页默认不进 sitemap 主推送面（列表页已在 sitemap）；长文需求后续再细化
        pass
    if c.status != "published":
        return None
    url = public_path(c, settings.site_url.rstrip("/"))
    return rebuild.trigger_rebuild([url])
