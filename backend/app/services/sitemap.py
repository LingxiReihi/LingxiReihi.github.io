"""sitemap.xml / sitemap.txt 生成（内存缓存，发布/下架事件失效）。docs/backend-architecture.md §10.2。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import Content

SECTION_URLS = [("/", "hourly"), ("/blog", "daily"), ("/models", "daily"),
                ("/chats", "hourly"), ("/about", "weekly")]
TYPE_PATH = {"article": "blog", "model": "models"}   # chat 详情用 /chats/{id}

_cache: dict[str, str] = {}


def invalidate() -> None:
    _cache.clear()


def _base() -> str:
    return settings.site_url.rstrip("/")


async def build(db: AsyncSession, fmt: str) -> str:
    if fmt in _cache:
        return _cache[fmt]
    rows = (await db.execute(
        select(Content.type, Content.id, Content.slug, Content.updated_at).where(
            Content.status == "published").order_by(Content.updated_at.desc()))).all()

    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    txt: list[str] = []

    def add(loc: str, lastmod, changefreq: str):
        txt.append(loc)
        lm = f"<lastmod>{lastmod:%Y-%m-%dT%H:%M:%SZ}</lastmod>" if lastmod is not None else ""
        xml.append(f"<url><loc>{loc}</loc>{lm}<changefreq>{changefreq}</changefreq></url>")

    for p, freq in SECTION_URLS:
        add(f"{_base()}{p}", None, freq)
    for type_, cid, slug, updated in rows:
        if type_ == "chat":
            add(f"{_base()}/chats/{cid}", updated, "weekly")
        elif slug:
            add(f"{_base()}/{TYPE_PATH[type_]}/{slug}", updated, "weekly")
    xml.append("</urlset>")
    result = "\n".join(xml) if fmt == "xml" else "\n".join(txt)
    _cache[fmt] = result
    return result
