"""请求访问日志中间件：每请求一行写 access.log（/media 静态与 OPTIONS 预检跳过）。"""
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..core.logs import access_logger

_SANITIZE = re.compile(r"[|\r\n]+")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        try:
            path = request.url.path
            if request.method != "OPTIONS" and not path.startswith(("/media", "/api/docs", "/api/openapi")):
                ms = (time.perf_counter() - start) * 1000
                ip = request.client.host if request.client else "-"
                ua = _SANITIZE.sub(" ", request.headers.get("user-agent", ""))[:80]
                access_logger.info(f"{request.method}|{path[:200]}|{response.status_code}|{ms:.0f}ms|{ip}|{ua}")
        except Exception:  # 日志失败不影响响应
            pass
        return response
