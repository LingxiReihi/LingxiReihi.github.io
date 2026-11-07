"""标签 CRUD + 站点设置分组读写（Flow G）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx, get_current_admin
from ...core.errors import AppException, ErrorCode, ok
from ...core.text import slugify
from ...models import AdminGrant, Column, Content, Tag, User, content_media, content_tags
from ...schemas.admin import SETTINGS_GROUPS, ColumnReq, TagReq
from ...services.settings import get_group, redact_group, set_group
from ...services import sitemap

tags_router = APIRouter(prefix="/tags", tags=["admin-tags"])
settings_router = APIRouter(prefix="/settings", tags=["admin-settings"])
columns_router = APIRouter(prefix="/columns", tags=["admin-columns"])


def _column_dict(c: Column, count: int, can_manage: bool = True) -> dict:
    return {"id": c.id, "name": c.name, "slug": c.slug, "type": c.type, "summary": c.summary,
            "sort_order": c.sort_order, "parent_id": c.parent_id, "count": int(count),
            "can_manage": can_manage}


async def _validate_parent(db, parent_id: int | None, type_: str, self_id: int | None = None) -> int | None:
    """父栏目须同类型；新节点深度 ≤3；不得选自身或后代作父（防环）。"""
    if parent_id is None:
        return None
    parent = await db.get(Column, parent_id)
    if not parent:
        raise AppException(ErrorCode.BAD_REQUEST, "上级栏目不存在")
    if parent.type != type_:
        raise AppException(ErrorCode.BAD_REQUEST, "上级栏目须为同一内容类型")
    if self_id is not None:
        node = parent
        while node:
            if node.id == self_id:
                raise AppException(ErrorCode.BAD_REQUEST, "不能将栏目挂到自己的下级")
            node = await db.get(Column, node.parent_id) if node.parent_id else None
    depth, cur = 1, parent
    while cur.parent_id:
        cur = await db.get(Column, cur.parent_id)
        depth += 1
        if depth > 2:
            raise AppException(ErrorCode.BAD_REQUEST, "栏目最多支持三级")
    return parent_id


@tags_router.get("")
async def list_tags(type: str | None = None, db: AsyncSession = Depends(get_db),
                    _: User = Depends(get_current_admin)):
    stmt = (select(Tag, func.count(content_tags.c.content_id))
            .join(content_tags, content_tags.c.tag_id == Tag.id, isouter=True)
            .group_by(Tag.id).order_by(Tag.name))
    if type:
        stmt = stmt.where(Tag.type == type)
    rows = (await db.execute(stmt)).all()
    return ok({"items": [{"id": t.id, "name": t.name, "slug": t.slug, "type": t.type,
                          "count": int(c)} for t, c in rows]})


@tags_router.post("")
async def create_tag(body: TagReq, db: AsyncSession = Depends(get_db),
                     ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("tag:manage", subject="标签管理")
    if (await db.execute(select(Tag).where(Tag.name == body.name, Tag.type == body.type))).scalar_one_or_none():
        raise AppException(ErrorCode.CONFLICT, "标签已存在")
    import secrets
    slug = slugify(body.name) or f"t-{secrets.token_hex(3)}"
    if (await db.execute(select(Tag).where(Tag.slug == slug, Tag.type == body.type))).scalar_one_or_none():
        slug = f"{slug}-{secrets.token_hex(2)}"
    t = Tag(name=body.name, slug=slug, type=body.type)
    db.add(t)
    await db.commit()
    return ok({"id": t.id, "name": t.name, "slug": t.slug, "type": t.type})


@tags_router.put("/{tag_id}")
async def rename_tag(tag_id: int, body: TagReq, db: AsyncSession = Depends(get_db),
                     ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("tag:manage", subject="标签管理")
    t = await db.get(Tag, tag_id)
    if not t:
        raise AppException(ErrorCode.NOT_FOUND, "标签不存在")
    dup = (await db.execute(select(Tag).where(Tag.name == body.name, Tag.type == t.type,
                                              Tag.id != tag_id))).scalar_one_or_none()
    if dup:
        raise AppException(ErrorCode.CONFLICT, "标签名已存在")
    t.name = body.name
    await db.commit()
    return ok({"id": t.id, "name": t.name, "slug": t.slug, "type": t.type})


@tags_router.delete("/{tag_id}")
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db),
                     ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("tag:manage", subject="标签管理")
    t = await db.get(Tag, tag_id)
    if not t:
        raise AppException(ErrorCode.NOT_FOUND, "标签不存在")
    detached = (await db.execute(
        select(func.count()).select_from(content_tags).where(content_tags.c.tag_id == tag_id)
    )).scalar_one()
    await db.execute(delete(content_tags).where(content_tags.c.tag_id == tag_id))
    await db.delete(t)
    await db.commit()
    return ok({"deleted": tag_id, "detached": int(detached)})


# ── 栏目 ──

async def _column_counts(db: AsyncSession) -> dict[int, int]:
    rows = await db.execute(
        select(Content.column_id, func.count()).where(Content.column_id.is_not(None))
        .group_by(Content.column_id))
    return {cid: int(c) for cid, c in rows.all() if cid is not None}


@columns_router.get("")
async def list_columns(type: str | None = None, db: AsyncSession = Depends(get_db),
                       ctx: AdminContext = Depends(get_admin_ctx)):
    stmt = select(Column)
    if type:
        stmt = stmt.where(Column.type == type)
    cols = (await db.execute(stmt.order_by(Column.sort_order, Column.id))).scalars().all()
    counts = await _column_counts(db)
    return ok({"items": [_column_dict(c, counts.get(c.id, 0),
                                      ctx.can("column:manage", column_id=c.id)) for c in cols]})


@columns_router.post("")
async def create_column(body: ColumnReq, db: AsyncSession = Depends(get_db),
                        ctx: AdminContext = Depends(get_admin_ctx)):
    # 新栏目没有 id，只能凭全局 column:manage 创建
    ctx.need("column:manage", subject="栏目管理")
    import secrets
    if (await db.execute(select(Column).where(Column.name == body.name, Column.type == body.type)
                         )).scalar_one_or_none():
        raise AppException(ErrorCode.CONFLICT, "栏目已存在")
    slug = body.slug.strip() if body.slug and body.slug.strip() else (slugify(body.name) or f"col-{secrets.token_hex(3)}")
    if (await db.execute(select(Column).where(Column.slug == slug, Column.type == body.type)
                         )).scalar_one_or_none():
        raise AppException(ErrorCode.CONFLICT, "slug 已存在", data={"field": "slug"})
    c = Column(name=body.name, slug=slug, type=body.type, summary=body.summary,
               sort_order=body.sort_order, parent_id=await _validate_parent(db, body.parent_id, body.type))
    db.add(c)
    await db.commit()
    sitemap.invalidate()
    return ok(_column_dict(c, 0))


@columns_router.put("/{column_id}")
async def update_column(column_id: int, body: ColumnReq, db: AsyncSession = Depends(get_db),
                        ctx: AdminContext = Depends(get_admin_ctx)):
    c = await db.get(Column, column_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "栏目不存在")
    ctx.need_scoped("column:manage", column_id=c.id, column_name=c.name, subject="栏目管理")
    dup = (await db.execute(select(Column).where(Column.name == body.name, Column.type == c.type,
                                                 Column.id != column_id))).scalar_one_or_none()
    if dup:
        raise AppException(ErrorCode.CONFLICT, "栏目名已存在")
    if body.slug and body.slug.strip() and body.slug.strip() != c.slug:
        ns = body.slug.strip()
        if (await db.execute(select(Column).where(Column.slug == ns, Column.type == c.type,
                                                  Column.id != column_id))).scalar_one_or_none():
            raise AppException(ErrorCode.CONFLICT, "slug 已存在", data={"field": "slug"})
        c.slug = ns
    c.name, c.summary, c.sort_order = body.name, body.summary, body.sort_order
    c.parent_id = await _validate_parent(db, body.parent_id, c.type, self_id=c.id)
    await db.commit()
    sitemap.invalidate()
    counts = await _column_counts(db)
    return ok(_column_dict(c, counts.get(c.id, 0)))


@columns_router.delete("/{column_id}")
async def delete_column(column_id: int, db: AsyncSession = Depends(get_db),
                        ctx: AdminContext = Depends(get_admin_ctx)):
    c = await db.get(Column, column_id)
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "栏目不存在")
    ctx.need_scoped("column:manage", column_id=c.id, column_name=c.name, subject="栏目管理")
    if (await db.execute(select(Column.id).where(Column.parent_id == column_id).limit(1))).first():
        raise AppException(ErrorCode.BAD_REQUEST, "请先删除该栏目下的子栏目")
    rows = (await db.execute(select(func.count()).select_from(Content)
                             .where(Content.column_id == column_id))).scalar_one()
    # 删除会把栏目下所有内容 column_id 置空 —— 触及他人内容就不是「栏目管理权」能覆盖的写操作
    foreign = (await db.execute(select(func.count()).select_from(Content).where(
        Content.column_id == column_id,
        or_(Content.created_by_id != ctx.user.id, Content.created_by_id.is_(None))))).scalar_one()
    if foreign and not ctx.can("column:manage"):
        raise AppException(ErrorCode.FORBIDDEN,
                           f"栏目「{c.name}」下还有 {foreign} 篇不属于你的内容，删除会把它们移出栏目，需要全局栏目管理权")
    await db.execute(sa_update(Content).where(Content.column_id == column_id).values(column_id=None))
    # scope_id 无外键，且 SQLite 会复用最大 rowid：不清理就等于把死授权留给下一个人
    await db.execute(delete(AdminGrant).where(AdminGrant.scope_type == "column",
                                             AdminGrant.scope_id == column_id))
    await db.delete(c)
    await db.commit()
    sitemap.invalidate()
    return ok({"deleted": column_id, "detached": int(rows)})


@settings_router.get("")
async def get_all_settings(db: AsyncSession = Depends(get_db),
                           _: User = Depends(get_current_admin)):
    return ok({g: redact_group(g, await get_group(db, g)) for g in SETTINGS_GROUPS})


@settings_router.put("/{group}")
async def put_group(group: str, body: dict, db: AsyncSession = Depends(get_db),
                    ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("setting:manage", subject="站点设置")
    if group not in SETTINGS_GROUPS:
        raise AppException(ErrorCode.BAD_REQUEST, f"未知设置分组 {group}")
    data = await set_group(db, group, body)
    sitemap.invalidate()   # 首页/导航变更影响预渲染枚举
    return ok({group: data})
