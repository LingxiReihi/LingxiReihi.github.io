"""根级 SEO 公开端点：sitemap / robots / 验证文件（经 Caddy 转发，docs/backend-architecture.md §8）。"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_db
from ..services import sitemap

router = APIRouter(tags=["seo-public"])

ROBOTS = """User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/

Sitemap: {site}/sitemap.xml
"""


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap_xml(db: AsyncSession = Depends(get_db)):
    return PlainTextResponse(await sitemap.build(db, "xml"), media_type="application/xml")


@router.get("/sitemap.txt", response_class=PlainTextResponse)
async def sitemap_txt(db: AsyncSession = Depends(get_db)):
    return PlainTextResponse(await sitemap.build(db, "txt"), media_type="text/plain")


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return PlainTextResponse(ROBOTS.format(site=settings.site_url.rstrip("/")), media_type="text/plain")


@router.get("/{filename}", response_class=Response, include_in_schema=False)
async def baidu_verify(filename: str):
    if settings.baidu_verify_name and filename == settings.baidu_verify_name:
        return PlainTextResponse(settings.baidu_verify_content, media_type="text/html")
    from ..core.errors import AppException, ErrorCode
    raise AppException(ErrorCode.NOT_FOUND, "Not Found")
