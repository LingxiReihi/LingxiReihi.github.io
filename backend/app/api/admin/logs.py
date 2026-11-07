"""日志查看与导出（后台）：文件列表 / tail 预览 / 单文件下载 / 全部打包 zip。

文件名严格白名单（app|access .log[.1-5]），防目录穿越。
"""
import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse

from ...core.deps import AdminContext, get_admin_ctx
from ...core.errors import AppException, ErrorCode, ok
from ...core.logs import log_dir

router = APIRouter(prefix="/logs", tags=["admin-logs"])

NAME_RE = re.compile(r"^(?:app|access)\.log(?:\.[1-5])?$")


async def _log_viewer(ctx: AdminContext = Depends(get_admin_ctx)) -> AdminContext:
    ctx.need("log:view", subject="运行日志")
    return ctx


def _safe(file: str) -> Path:
    if not NAME_RE.match(file or ""):
        raise AppException(ErrorCode.BAD_REQUEST, "非法日志文件名")
    p = log_dir() / file
    if not p.is_file():
        raise AppException(ErrorCode.NOT_FOUND, "日志文件不存在")
    return p


@router.get("/files")
async def list_files(_: AdminContext = Depends(_log_viewer)):
    out = []
    for p in sorted(log_dir().iterdir()):
        if p.is_file() and NAME_RE.match(p.name):
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size,
                        "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})
    return ok({"items": out})


@router.get("/tail")
async def tail(file: str = "app.log", lines: int = Query(300, ge=1, le=5000),
               grep: str | None = None, _: AdminContext = Depends(_log_viewer)):
    p = _safe(file)
    data = p.read_bytes()
    window = lines * 512  # 估算读取尾部窗口，避免整读大文件
    if len(data) > window:
        data = data[-window:]
    ls = data.decode("utf-8", "replace").splitlines()
    if grep:
        ls = [l for l in ls if grep.lower() in l.lower()]
    return ok({"total": len(ls), "lines": ls[-lines:]})


@router.get("/download")
async def download(file: str, _: AdminContext = Depends(_log_viewer)):
    p = _safe(file)
    return FileResponse(p, filename=p.name, media_type="text/plain; charset=utf-8")


@router.get("/archive")
async def archive(_: AdminContext = Depends(_log_viewer)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(log_dir().iterdir()):
            if p.is_file() and NAME_RE.match(p.name):
                z.write(p, p.name)
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="logs-{stamp}.zip"'})
