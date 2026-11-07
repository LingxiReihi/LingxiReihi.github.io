"""PV/UV 采集中间件（docs/backend-architecture.md §6）。"""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..core.db import SessionLocal
from ..models import Content, ViewEvent

TARGET = re.compile(r"^/api/v1/(?:(?:posts|models)/([^/?]+)|home|about|chats/?$|search)")
BOT_UA = re.compile(r"(?:baiduspider|bingbot|googlebot|spider|crawl|bot\b|headless)", re.I)


def page_referrer(request: Request) -> str:
    """前端上报的落地来源：同源 XHR 的 referer 恒等于本站页面 URL，真来源只能由前端带。"""
    raw = (request.headers.get("x-page-referrer") or "").strip()[:255]
    return raw if urlparse(raw).scheme in ("http", "https") else ""


def _day() -> int:
    return int(datetime.now(timezone.utc).strftime("%Y%m%d"))


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


class AccessTrackMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            await self._track(request, response.status_code)
        except Exception:  # 采集失败不影响响应
            pass
        return response

    async def _track(self, request: Request, status_code: int) -> None:
        if request.method != "GET":
            return
        path = request.url.path
        m = TARGET.match(path)
        if not m:
            return
        ua = request.headers.get("user-agent", "")
        if BOT_UA.search(ua):
            return
        ip = request.client.host if request.client else "0"
        if ip in ("127.0.0.1", "::1") and "track_local=1" not in str(request.url.query):
            # 本地开发默认不计数，避免污染统计；?track_local=1 强制采集
            return
        day = _day()
        content_id = None
        if m.group(1):
            async with SessionLocal() as db:
                from sqlalchemy import select
                content_id = (await db.execute(
                    select(Content.id).where(Content.slug == m.group(1)))).scalar_one_or_none()
        async with SessionLocal() as db:
            db.add(ViewEvent(
                day=day, path=path[:255], content_id=content_id,
                referrer=(page_referrer(request) or request.headers.get("referer") or "")[:255],
                ip_hash=_h(ip, str(day), settings_salt()), ua_hash=_h(ua[:120], str(day), settings_salt()),
                status_code=status_code))
            await db.commit()


def settings_salt() -> str:
    from ..core.config import settings
    return hashlib.sha256(settings.jwt_secret.encode()).hexdigest()[:16]
