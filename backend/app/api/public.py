"""公开只读 API（免鉴权）：docs/api-reference.md §3。"""
import time
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import jwt
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_db
from ..core.deps import get_page
from ..core.errors import AppException, ErrorCode, ok
from ..schemas import public as P
from ..services import content as svc
from ..services import profiles
from ..services.settings import get_group, get_public_config

router = APIRouter(tags=["public"])

PREVIEW_MINUTES = 15
LIKE_COOLDOWN_SECONDS = 10
_like_cooldown: dict[str, float] = {}


def _check_like_cooldown(request: Request, content_id: int, action: str = "like") -> None:
    """同 IP 对同内容 10s 冷却（点赞/取消分开计），防误触/简单刷量（无账号体系下的尽力而为）。"""
    now = time.time()
    if len(_like_cooldown) > 4096:  # 粗清理，避免长跑内存膨胀
        for k, t in list(_like_cooldown.items()):
            if now - t > LIKE_COOLDOWN_SECONDS:
                _like_cooldown.pop(k, None)
    ip = request.client.host if request.client else "0"
    key = f"{ip}:{content_id}:{action}"
    last = _like_cooldown.get(key, 0)
    if now - last < LIKE_COOLDOWN_SECONDS:
        raise AppException(ErrorCode.RATE_LIMITED, "操作太频繁，请稍后再试")
    _like_cooldown[key] = now


def make_preview_token(content_id: int) -> str:
    return jwt.encode({"sub": "preview", "cid": content_id, "type": "preview",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=PREVIEW_MINUTES)},
                      settings.jwt_secret, algorithm="HS256")


def _verify_preview_token(token: str, content_id: int) -> None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise AppException(ErrorCode.FORBIDDEN, "预览链接无效或已过期")
    if payload.get("type") != "preview" or payload.get("cid") != content_id:
        raise AppException(ErrorCode.FORBIDDEN, "预览链接无效或已过期")


async def _detail(db: AsyncSession, c) -> dict:
    d = P.ContentDetail.from_content_full(c, author=await profiles.author_of(db, c))
    prev, nxt = await svc.neighbors(db, c)
    rel = await svc.related(db, c)
    d.prev, d.next, d.related = prev, nxt, [P.ContentOut.from_content(x) for x in rel]
    return d.model_dump()


@router.get("/home")
async def home(db: AsyncSession = Depends(get_db)):
    posts, _ = await svc.list_published(db, "article", None, None, 1, 3)
    chats, _ = await svc.cursor_chats(db, 2, None, None)
    cfg = await get_public_config(db)
    return ok({"profile": cfg["profile"],
               "recent_posts": [P.ContentOut.from_content(c) for c in posts],
               "recent_chats": [P.ContentOut.from_content(c) for c in chats],
               "latest": [P.ContentOut.from_content(c) for c in await svc.latest_contents(db)],
               "hot": [P.HotOut.from_row(c, n, s) for c, n, s in await svc.hot_contents(db)],
               "team": await profiles.home_team(db)})


@router.get("/posts")
async def list_posts(q: str | None = None, tag: str | None = None, column: str | None = None,
                     column_direct: bool = False,
                     pg=Depends(get_page), db: AsyncSession = Depends(get_db)):
    items, total = await svc.list_published(db, "article", q, tag, pg.page, pg.page_size, column, column_direct)
    return ok({"total": total, "page": pg.page, "page_size": pg.page_size,
               "items": [P.ContentOut.from_content(c) for c in items]})


@router.get("/posts/{slug}")
async def post_detail(slug: str, db: AsyncSession = Depends(get_db)):
    c = await svc.get_published(db, "article", slug)
    return ok(await _detail(db, c))


async def _do_like(request: Request, type_: str, slug: str, db: AsyncSession, *, unlike: bool = False) -> dict:
    c = await svc.get_published(db, type_, slug)
    _check_like_cooldown(request, c.id, "unlike" if unlike else "like")
    c.likes = max(0, c.likes - 1) if unlike else c.likes + 1
    await db.commit()
    return {"id": c.id, "likes": c.likes}


@router.post("/posts/{slug}/like")
async def like_post(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return ok(await _do_like(request, "article", slug, db))


@router.post("/posts/{slug}/unlike")
async def unlike_post(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return ok(await _do_like(request, "article", slug, db, unlike=True))


@router.post("/models/{slug}/like")
async def like_model(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return ok(await _do_like(request, "model", slug, db))


@router.post("/models/{slug}/unlike")
async def unlike_model(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return ok(await _do_like(request, "model", slug, db, unlike=True))


@router.get("/posts/{slug}/preview")
async def post_preview(slug: str, token: str = Query(...), db: AsyncSession = Depends(get_db)):
    c = await svc.get_draft_for_preview(db, "article", slug)
    _verify_preview_token(token, c.id)
    return ok(await _detail(db, c))


@router.get("/models")
async def list_models(kind: str = Query("all", pattern="^(all|3d|render|animation)$"),
                      q: str | None = None, tag: str | None = None, column: str | None = None,
                      column_direct: bool = False,
                      pg=Depends(get_page), db: AsyncSession = Depends(get_db)):
    items, total = await svc.list_published(db, "model", q, tag, pg.page, pg.page_size, column, column_direct)
    if kind != "all":
        items = [c for c in items if c.media_kind == kind]
        total = len(items)  # 个人站量级可接受；量大后改 SQL 条件
    return ok({"total": total, "page": pg.page, "page_size": pg.page_size,
               "items": [P.ContentOut.from_content(c) for c in items]})


@router.get("/models/{slug}")
async def model_detail(slug: str, db: AsyncSession = Depends(get_db)):
    c = await svc.get_published(db, "model", slug)
    return ok(await _detail(db, c))


@router.post("/models/{slug}/download")
async def model_download(slug: str, asset_id: int | None = None,
                         db: AsyncSession = Depends(get_db)):
    c = await svc.get_published(db, "model", slug)
    models = [a for a in c.assets if a.kind == "model3d"]
    asset = next((a for a in models if a.id == asset_id), None) if asset_id else (models[0] if models else None)
    if not asset:
        raise AppException(ErrorCode.NOT_FOUND, "该作品不提供下载")
    c.downloads += 1
    await db.commit()
    return ok({"url": f"/media/{asset.storage_key}", "filename": asset.filename})


@router.get("/chats")
async def list_chats(cursor: str | None = None, limit: int = Query(20, ge=1, le=50),
                     tag: str | None = None, column: str | None = None, column_direct: bool = False,
                     db: AsyncSession = Depends(get_db)):
    cur = None
    if cursor:
        import base64, json
        try:
            cur = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        except Exception:
            raise AppException(ErrorCode.BAD_REQUEST, "cursor 无效")
    items, nxt = await svc.cursor_chats(db, limit, cur, tag, column, column_direct)
    # 杂谈为短内容，列表直接携带 body_md 供前端折叠展示
    return ok({"items": [{**P.ContentOut.from_content(c).model_dump(), "body_md": c.body_md}
                         for c in items], "next_cursor": nxt})


@router.get("/chats/{content_id}")
async def chat_detail(content_id: int, db: AsyncSession = Depends(get_db)):
    c = await svc.get_by_id(db, content_id)
    if c.type != "chat":
        raise AppException(ErrorCode.NOT_FOUND, "内容不存在")
    return ok(await _detail(db, c))


@router.get("/about")
async def about(db: AsyncSession = Depends(get_db)):
    """关于页资料 = 顶级管理员那一行 + 勾选露出的「管理团队」名单。"""
    return ok(await profiles.about_payload(db))


@router.get("/site-config")
async def site_config(db: AsyncSession = Depends(get_db)):
    return ok(await get_public_config(db))


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=64),
                 type: str | None = Query(None, pattern="^(article|model|chat)$"),
                 db: AsyncSession = Depends(get_db)):
    items = await svc.search(db, q, type)
    return ok({"items": [P.ContentOut.from_content(c) for c in items]})


@router.get("/tags")
async def tags(type: str | None = None, db: AsyncSession = Depends(get_db)):
    return ok({"items": await svc.tags_with_counts(db, type)})


@router.get("/columns")
async def list_columns(type: str | None = None, db: AsyncSession = Depends(get_db)):
    return ok({"items": await svc.columns_with_counts(db, type)})


@router.get("/rss")
async def rss(db: AsyncSession = Depends(get_db)):
    items, _ = await svc.list_published(db, "article", None, None, 1, 20)
    site = await get_group(db, "site")
    title = site.get("title", "Blog")
    base = settings.site_url.rstrip("/")
    entries = []
    for c in items:
        pub = (c.published_at or c.created_at).strftime("%a, %d %b %Y %H:%M:%S +0000")
        link = f"{base}/blog/{c.slug}"
        entries.append(f"<item><title>{escape(c.title)}</title><link>{link}</link>"
                       f"<guid>{link}</guid><pubDate>{pub}</pubDate>"
                       f"<description>{escape(c.summary)}</description></item>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<rss version="2.0"><channel>'
           f"<title>{escape(title)}</title><link>{base}</link>"
           f"<description>{escape(site.get('description', ''))}</description>"
           + "".join(entries) + "</channel></rss>")
    return Response(content=xml, media_type="application/rss+xml")
