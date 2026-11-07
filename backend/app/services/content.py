"""公开内容查询（仅 published）。"""
import re

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import AppException, ErrorCode
from ..models import Comment, Content, Tag, content_tags

_slug_re = re.compile(r"^[\w\-]{1,200}$")

HOT_WEIGHTS = {"view": 1, "like": 8, "comment": 12}


def _like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _pub(type_: str):
    return select(Content).where(Content.type == type_, Content.status == "published")


def _tag_cond(tag: str):
    """tag 参数支持逗号分隔多选：每个标签生成一个 IN 子查询，叠加即 AND 语义（同时含所有所选标签）。"""
    conds = []
    for one in [s.strip() for s in tag.split(",") if s.strip()]:
        conds.append(Content.id.in_(
            select(content_tags.c.content_id).join(Tag, Tag.id == content_tags.c.tag_id)
            .where(or_(Tag.slug == one, Tag.name == one))))
    return conds


async def _column_ids(db: AsyncSession, column: str, type_: str, direct: bool = False) -> list[int]:
    """栏目筛选默认含子孙；direct=True 仅本级（目录栏展开父栏目取直属文章用）。"""
    from collections import defaultdict

    from ..models import Column
    cols = (await db.execute(select(Column).where(Column.type == type_))).scalars().all()
    root = next((c for c in cols if c.slug == column or c.name == column), None)
    if not root:
        return []
    if direct:
        return [root.id]
    kids: dict[int, list] = defaultdict(list)
    for c in cols:
        if c.parent_id:
            kids[c.parent_id].append(c)
    ids, stack = [root.id], [root]
    while stack:
        for ch in kids.get(stack.pop().id, []):
            ids.append(ch.id)
            stack.append(ch)
    return ids


async def list_published(db: AsyncSession, type_: str, q: str | None, tag: str | None,
                         page: int, page_size: int, column: str | None = None,
                         column_direct: bool = False) -> tuple[list[Content], int]:
    stmt = _pub(type_)
    cond = []
    if q:
        like = f"%{_like_escape(q)}%"
        cond.append(or_(Content.title.like(like), Content.summary.like(like),
                        Content.body_md.like(like)))
    if tag:
        cond.extend(_tag_cond(tag))
    if column:
        cond.append(Content.column_id.in_(await _column_ids(db, column, type_, column_direct)))
    if cond:
        stmt = stmt.where(*cond)
    total = (await db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = await db.execute(
        stmt.order_by(Content.published_at.desc(), Content.id.desc())
        .offset((page - 1) * page_size).limit(page_size))
    return list(rows.scalars().all()), total


async def get_published(db: AsyncSession, type_: str, slug: str) -> Content:
    if not _slug_re.match(slug or ""):
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    c = (await db.execute(_pub(type_).where(Content.slug == slug))).scalar_one_or_none()
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    return c


async def get_by_id(db: AsyncSession, content_id: int) -> Content:
    c = await db.get(Content, content_id)
    if not c or c.status != "published":
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    return c


async def get_draft_for_preview(db: AsyncSession, type_: str, slug: str) -> Content:
    c = (await db.execute(select(Content).where(Content.type == type_, Content.slug == slug)
                          .where(Content.status.in_(("draft", "published", "archived"))))).scalar_one_or_none()
    if not c:
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    return c


async def neighbors(db: AsyncSession, c: Content) -> tuple[dict | None, dict | None]:
    """同类型按 published_at 的前后篇。"""
    base = Content.type == c.type
    if not c.published_at:
        return None, None
    prev_ = (await db.execute(
        _pub("article" if c.type == "article" else c.type).where(base,
            Content.published_at < c.published_at)
        .order_by(Content.published_at.desc()).limit(1))).scalar_one_or_none()
    nxt = (await db.execute(
        select(Content).where(base, Content.status == "published",
                              Content.published_at > c.published_at)
        .order_by(Content.published_at.asc()).limit(1))).scalar_one_or_none()

    def brief(x: Content | None):
        return None if not x else {"slug": x.slug, "title": x.title, "cover": (
            f"/media/{x.cover_asset.storage_key}" if x.cover_asset else None)}
    return brief(prev_), brief(nxt)


async def related(db: AsyncSession, c: Content, n: int = 3) -> list[Content]:
    tag_ids = [t.id for t in c.tags]
    if not tag_ids:
        rows = await db.execute(_pub(c.type).where(Content.id != c.id)
                                .order_by(Content.published_at.desc()).limit(n))
        return list(rows.scalars().all())
    sibling_ids = select(content_tags.c.content_id).where(content_tags.c.tag_id.in_(tag_ids))
    rows = await db.execute(_pub(c.type).where(Content.id != c.id, Content.id.in_(sibling_ids))
                            .order_by(Content.published_at.desc()).limit(n))
    return list(rows.scalars().all())


async def latest_contents(db: AsyncSession, limit: int = 12) -> list[Content]:
    """跨类型最新（文章/模型/杂谈混排），首页第一段瀑布用。"""
    stmt = (select(Content).where(Content.status == "published")
            .order_by(Content.published_at.desc()).limit(limit))
    return list((await db.execute(stmt)).scalars().all())


async def hot_contents(db: AsyncSession, limit: int = 8) -> list[tuple[Content, int, int]]:
    """跨类型热门：score = 浏览×1 + 点赞×8 + 已过审评论×12。

    评论权重最高是因为它最稀有（本站先审后显，一条评论的含金量远高于一次浏览）。
    score 一并返回，前台只拿它画热度条 —— 权重别在前端再抄一份，否则两边迟早算得不一样。
    不做时间衰减：那会让「一篇老文永远占着热门位」，需要时再单独拍口径。
    """
    approved = (select(Comment.content_id.label("cid"), func.count().label("n"))
                .where(Comment.status == "approved").group_by(Comment.content_id).subquery())
    n = func.coalesce(approved.c.n, 0)
    score = (Content.view_count * HOT_WEIGHTS["view"] + Content.likes * HOT_WEIGHTS["like"]
             + n * HOT_WEIGHTS["comment"])
    stmt = (select(Content, n, score).outerjoin(approved, approved.c.cid == Content.id)
            .where(Content.status == "published")
            .order_by(score.desc(), Content.published_at.desc()).limit(limit))
    return [(c, cnt, sc) for c, cnt, sc in (await db.execute(stmt)).all()]


async def cursor_chats(db: AsyncSession, limit: int, cursor: dict | None,
                       tag: str | None, column: str | None = None,
                       column_direct: bool = False) -> tuple[list[Content], str | None]:
    stmt = _pub("chat")
    if tag:
        stmt = stmt.where(*_tag_cond(tag))
    if column:
        stmt = stmt.where(Content.column_id.in_(await _column_ids(db, column, "chat", column_direct)))
    if cursor:
        from datetime import datetime as _dt
        t, cid = _dt.fromisoformat(cursor["t"]), cursor["id"]
        stmt = stmt.where(or_(Content.published_at < t,
                              (Content.published_at == t) & (Content.id < cid)))
    rows = await db.execute(stmt.order_by(Content.published_at.desc(), Content.id.desc()).limit(limit + 1))
    items = list(rows.scalars().all())
    nxt = None
    if len(items) > limit:
        items = items[:limit]
        import base64, json
        last = items[-1]
        nxt = base64.urlsafe_b64encode(json.dumps(
            {"t": last.published_at.isoformat(), "id": last.id}).encode()).decode()
    return items, nxt


async def search(db: AsyncSession, q: str, type_: str | None, n: int = 20) -> list[Content]:
    like = f"%{_like_escape(q)}%"
    stmt = select(Content).where(Content.status == "published",
                                 or_(Content.title.like(like), Content.summary.like(like),
                                     Content.body_md.cast(String).like(like)))
    if type_:
        stmt = stmt.where(Content.type == type_)
    rows = await db.execute(stmt.order_by(Content.published_at.desc()).limit(n))
    return list(rows.scalars().all())


async def tags_with_counts(db: AsyncSession, type_: str | None = None) -> list[dict]:
    stmt = (select(Tag, func.count(Content.id))
            .join(content_tags, content_tags.c.tag_id == Tag.id, isouter=True)
            .join(Content, (Content.id == content_tags.c.content_id) & (Content.status == "published"))
            .group_by(Tag.id).order_by(func.count(Content.id).desc(), Tag.name))
    if type_:
        stmt = stmt.where(Tag.type == type_)
    rows = await db.execute(stmt)
    return [{"id": t.id, "name": t.name, "slug": t.slug, "type": t.type, "count": int(cnt)} for t, cnt in rows.all()]


async def columns_with_counts(db: AsyncSession, type_: str | None = None) -> list[dict]:
    """count = 本级直属；total = 自身 + 全部子孙（前台目录栏徽章用 total，与点进去的筛选结果同口径）。"""
    from ..models import Column
    stmt = (select(Column, func.count(Content.id))
            .outerjoin(Content, (Content.column_id == Column.id) & (Content.status == "published"))
            .group_by(Column.id).order_by(Column.sort_order, Column.id))
    if type_:
        stmt = stmt.where(Column.type == type_)
    rows = (await db.execute(stmt)).all()
    direct = {col.id: int(cnt) for col, cnt in rows}
    # 栏目按类型隔离且父栏目必同类型，所以子孙一定在本次取回的集合里；
    # 内容最多挂一个栏目（column_id 单 FK），逐层相加不会重复计数。
    kids: dict[int, list[int]] = {}
    for col, _cnt in rows:
        if col.parent_id in direct:
            kids.setdefault(col.parent_id, []).append(col.id)

    def subtree(cid: int) -> int:
        return direct[cid] + sum(subtree(k) for k in kids.get(cid, []))

    return [{"id": col.id, "name": col.name, "slug": col.slug, "type": col.type,
             "summary": col.summary, "parent_id": col.parent_id, "count": direct[col.id],
             "total": subtree(col.id)} for col, _cnt in rows]
