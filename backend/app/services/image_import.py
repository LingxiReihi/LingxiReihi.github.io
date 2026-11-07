"""Markdown 外链图片入库：识别 ![](https://…) → 服务端下载 → 存入素材库 → 回写站点全链地址。

为什么必须走服务端：浏览器直接 fetch 跨域图片会被 CORS 拦掉（多数图床不回
Access-Control-Allow-Origin），即使拿到 blob 也还是要再传一次。放在后端可以
一次完成下载 + 校验 + 落盘 + 入库。

命名规则：`{内容 slug}-{图片名}{扩展名}`，图片名取自 URL 末段（无扩展名时按
Content-Type 补齐）。同批重名追加 -2/-3，避免素材库里一堆同名条目。

本地链接（相对路径、本站地址含 www/apex 变体、本机地址、data: 等内联数据）一律
跳过下载与存储，只在结果的 skipped 里回报原因；回写的是 `{SITE_URL}/media/…`
绝对地址，所以本站素材的完整 URL 会留在正文里，重复执行不会重复入库。
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
from urllib.parse import unquote, urljoin, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.errors import AppException, ErrorCode
from ..models import Content
from .media import MAX_SIZE, WHITELIST, store_upload

# 只认 Markdown 图片语法：![alt](url "title")，URL 允许用 <> 包裹（含空格时必须）
_MD_IMG = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\(\s*(?P<url><[^<>]*>|[^\s)]+)"
    r"(?:\s+(?P<title>\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)

_IMAGE_EXTS = {ext for ext, (kind, _) in WHITELIST.items() if kind == "image"}
_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
             "image/gif": ".gif", "image/avif": ".avif"}

MAX_BYTES = MAX_SIZE["image"]
MAX_FETCH = 30          # 单篇一次最多抓 30 张：防止误把整站图片拖下来
TIMEOUT = 15.0
MAX_HOPS = 3            # 重定向跳数上限；每一跳都要重新过内网校验
UA = "Mozilla/5.0 (compatible; personal-web-image-import/1.0; +https://lingxi-reihi.cn)"


_LOOPBACK = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
_NON_FETCH_SCHEMES = ("data", "blob", "javascript", "mailto", "tel", "about")


def _unwrap(raw: str) -> str:
    return raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw


def local_hosts() -> set[str]:
    """「算本站」的主机名集合：配置域名的 www/apex 变体 + 本机调试的几种写法。

    回写用的是绝对地址，本站素材的完整 URL 会一直留在正文里；本机调试时又可能
    写成 localhost 或 127.0.0.1，所以两边都要认，否则重复点一次就会把自家图片再下一遍。
    """
    hosts = set(_LOOPBACK)
    host = urlparse((settings.site_url or "").strip()).hostname
    if host:
        host = host.lower()
        if host not in _LOOPBACK:
            hosts.add(host)
            hosts.add(host[4:] if host.startswith("www.") else f"www.{host}")
    return hosts


def local_reason(url: str, hosts: set[str] | None = None) -> str:
    """判断是不是「本地链接」：返回原因文案，空串表示这是需要下载的外链。"""
    raw = (url or "").strip()
    if not raw:
        return "空地址"
    p = urlparse(raw)
    scheme = (p.scheme or "").lower()
    if scheme in _NON_FETCH_SCHEMES:
        return "内联数据"
    if not scheme:
        # 相对路径、根路径、以及 //host/x.png 这种协议相对地址：不下载，保持原样
        return "站内相对路径"
    if scheme not in ("http", "https"):
        return f"不支持的协议 {scheme}"
    host = (p.hostname or "").lower()
    if not host:
        return "站内相对路径"
    if host in _LOOPBACK:
        return "本机地址"
    if host in (hosts or set()):
        return "本站地址"
    return ""


def is_external(url: str, hosts: set[str] | None = None) -> bool:
    """需要下载入库的才算外链：本地链接（本站/本机/相对路径/data:）一律跳过。"""
    return local_reason(url, hosts) == ""


async def _assert_public(host: str) -> None:
    """SSRF 防护：域名解析出的任一地址落在内网/环回/链路本地就拒绝。

    服务端替用户抓任意 URL 是个典型 SSRF 面（169.254.169.254 元数据、
    127.0.0.1 内部服务），必须逐地址校验而不是只看字面量。
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, 0, socket.SOCK_STREAM)
    except OSError:
        raise AppException(ErrorCode.BAD_REQUEST, f"域名无法解析：{host}")
    if not infos:
        raise AppException(ErrorCode.BAD_REQUEST, f"域名无法解析：{host}")
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            raise AppException(ErrorCode.BAD_REQUEST, "地址无法识别")
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise AppException(ErrorCode.FORBIDDEN, "不允许抓取内网地址")


async def _fetch(url: str, transport: httpx.AsyncBaseTransport | None = None) -> tuple[bytes, str]:
    """下载一张图，返回 (字节, Content-Type)。手动跟随重定向，每一跳都重新校验。"""
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA},
                                 transport=transport, follow_redirects=False) as client:
        for _ in range(MAX_HOPS + 1):
            p = urlparse(url)
            if p.scheme not in ("http", "https") or not p.hostname:
                raise AppException(ErrorCode.BAD_REQUEST, "只支持 http/https 图片地址")
            await _assert_public(p.hostname)
            async with client.stream("GET", url) as r:
                if 300 <= r.status_code < 400 and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                if r.status_code >= 400:
                    raise AppException(ErrorCode.BAD_REQUEST, f"源站返回 {r.status_code}")
                ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not ctype.startswith("image/"):
                    raise AppException(ErrorCode.UNSUPPORTED_TYPE,
                                       f"不是图片（{ctype or '未知类型'}）")
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_BYTES:
                        raise AppException(ErrorCode.TOO_LARGE,
                                           f"超出大小限制（≤{MAX_BYTES // 1024 // 1024}MB）")
                if not buf:
                    raise AppException(ErrorCode.BAD_REQUEST, "图片内容为空")
                return bytes(buf), ctype
        raise AppException(ErrorCode.BAD_REQUEST, "重定向次数过多")


def _stem_ext(url: str, ctype: str) -> tuple[str, str]:
    """从 URL 末段取图片名与扩展名；扩展名不可信时按 Content-Type 补齐。"""
    name = unquote(urlparse(url).path).rsplit("/", 1)[-1]
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in _IMAGE_EXTS:
        inner = os.path.splitext(stem)[1].lower()      # 形如 foo.png?x=1 已被 path 去掉，这里兜底 foo.png.jpg
        ext = inner if inner in _IMAGE_EXTS else _MIME_EXT.get(ctype, ".png")
    # 只保留字母数字/下划线/连字符/中文，其余压成单连字符
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", stem).strip("-_")
    return (stem or "img")[:60], ext


def _asset_name(slug: str, stem: str, ext: str, used: set[str]) -> str:
    base = f"{slug}-{stem}" if slug else stem
    name = f"{base}{ext}"
    n = 2
    while name.lower() in used:
        name = f"{base}-{n}{ext}"
        n += 1
    used.add(name.lower())
    return name[:255]


async def import_markdown_images(db: AsyncSession, content: Content, body_md: str, *,
                                 base_url: str = "",
                                 transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """把正文里的外链图片全部搬到素材库，返回改写后的 Markdown 与逐条结果。

    base_url 是站点对外地址：回写用 `{base_url}/media/…` 绝对地址，导出到站外也不会丢图。
    不落库：调用方拿到 body_md 自行保存，避免用编辑器里的未保存稿覆盖服务端正文。
    """
    md = body_md or ""
    hosts = local_hosts()
    seen: set[str] = set()
    urls: list[str] = []
    skipped: list[dict] = []
    for m in _MD_IMG.finditer(md):
        u = _unwrap(m.group("url"))
        if u in seen:
            continue
        seen.add(u)
        reason = local_reason(u, hosts)
        if reason:
            skipped.append({"src": u, "reason": reason})
            continue
        urls.append(u)
    total = len(seen)
    if not urls:
        return {"body_md": md, "imported": [], "failed": [], "skipped": skipped, "total": total}

    overflow = urls[MAX_FETCH:]
    urls = urls[:MAX_FETCH]

    slug = (content.slug or f"c-{content.id}").strip()
    prefix = base_url.rstrip("/")
    category = "render" if content.type == "model" else "blog"
    mapping: dict[str, str] = {}
    imported: list[dict] = []
    failed: list[dict] = []
    used: set[str] = set()

    for u in urls:
        try:
            data, ctype = await _fetch(u, transport)
            stem, ext = _stem_ext(u, ctype)
            filename = _asset_name(slug, stem, ext, used)
            asset = await store_upload(db, filename, ctype, data, category)
            local = f"{prefix}/media/{asset.storage_key}"
            mapping[u] = local
            imported.append({"src": u, "url": local, "filename": asset.filename,
                             "asset_id": asset.id, "size": asset.size})
        except AppException as e:
            failed.append({"src": u, "reason": e.message})
        except Exception as e:                                  # 网络类异常不中断整批
            failed.append({"src": u, "reason": f"下载失败：{e.__class__.__name__}"})
    for u in overflow:
        failed.append({"src": u, "reason": f"单次最多处理 {MAX_FETCH} 张，请分批导入"})

    def _repl(m: re.Match) -> str:
        new = mapping.get(_unwrap(m.group("url")))
        if not new:
            return m.group(0)
        title = m.group("title")
        return f"![{m.group('alt')}]({new}{(' ' + title) if title else ''})"

    new_md = _MD_IMG.sub(_repl, md) if mapping else md
    return {"body_md": new_md, "imported": imported, "failed": failed,
            "skipped": skipped, "total": total}
