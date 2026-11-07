"""媒体上传：白名单校验 / uuid 重命名 / sha256 秒传 / webp 缩略图。

组织（分类、重命名）一律只改数据库字段：`storage_key` 是素材的永久地址，
一旦落盘就不再变，已有正文链接永远有效。物理搬家会换 URL，历史文章与外部
引用会集体失效，所以这里不做。
"""
import hashlib
import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.errors import AppException, ErrorCode
from ..models import Content, MediaAsset, content_media

# ext -> (kind, allowed mimes)
WHITELIST: dict[str, tuple[str, tuple[str, ...]]] = {
    ".png": ("image", ("image/png",)),
    ".jpg": ("image", ("image/jpeg",)), ".jpeg": ("image", ("image/jpeg",)),
    ".webp": ("image", ("image/webp",)), ".gif": ("image", ("image/gif",)),
    ".avif": ("image", ("image/avif",)),
    # 3D 只收两种：glb 供在线预览，zip 承载 obj/fbx/blend/max 等工程文件及其材质贴图
    ".glb": ("model3d", ("model/gltf-binary", "application/octet-stream")),
    ".zip": ("model3d", ("application/zip", "application/x-zip-compressed", "application/octet-stream")),
    ".mp4": ("video", ("video/mp4",)), ".webm": ("video", ("video/webm",)),
}
MAX_SIZE = {"image": 5 * 1024 * 1024, "model3d": 200 * 1024 * 1024, "video": 200 * 1024 * 1024}
# 这些格式不再单独收录，命中时给出「打包成 zip」的指引而非笼统的「不支持」
PACKABLE_EXTS = {".gltf", ".fbx", ".obj", ".mtl", ".blend", ".max", ".usdz", ".stl",
                 ".bin", ".tga", ".tif", ".tiff", ".exr", ".hdr", ".ktx2", ".dds", ".dae", ".3ds"}
THUMB_WIDTH = 640
# 压缩包内容清单条目上限，防超大包把 JSON 列撑爆
ZIP_MAX_ENTRIES = 2000
CATEGORIES = ("blog", "avatar", "render", "model", "site")


def _check_category(category: str | None) -> None:
    if category is not None and category not in CATEGORIES:
        raise AppException(ErrorCode.BAD_REQUEST, f"未知分类 {category}")


def _sniff_kind(filename: str, mime: str) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext not in WHITELIST:
        if ext in PACKABLE_EXTS:
            raise AppException(ErrorCode.UNSUPPORTED_TYPE,
                               f"{ext} 不单独收录：请把模型连同材质贴图打包成 .zip 上传（预览用请导出 .glb）")
        raise AppException(ErrorCode.UNSUPPORTED_TYPE, f"不支持的文件类型 {ext or '(无扩展名)'}")
    kind, mimes = WHITELIST[ext]
    if mime and mime != "application/octet-stream" and mime not in mimes:
        raise AppException(ErrorCode.UNSUPPORTED_TYPE, f"MIME {mime} 与扩展名不符")
    return kind, ext


def _zip_index(data: bytes) -> list[dict]:
    """只读 zip 中央目录拿内容清单（含层级路径），不解压、不落盘。"""
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
    except Exception:
        raise AppException(ErrorCode.BAD_REQUEST, "压缩包无法解析，请确认是完整的 zip 文件")
    out: list[dict] = []
    for info in infos:
        path = info.filename.replace("\\", "/").strip("/")
        if not path or info.is_dir() or ".." in path.split("/"):
            continue
        out.append({"path": path, "size": info.file_size})
        if len(out) >= ZIP_MAX_ENTRIES:
            break
    return out


async def store_upload(db: AsyncSession, filename: str, mime: str, data: bytes,
                       category: str | None = None) -> MediaAsset:
    _check_category(category)
    kind, ext = _sniff_kind(filename, mime)
    limit = MAX_SIZE[kind]
    if len(data) > limit:
        raise AppException(ErrorCode.TOO_LARGE,
                           f"超出大小限制（{ext} ≤ {limit // 1024 // 1024}MB）")
    entries = _zip_index(data) if ext == ".zip" else None
    sha = hashlib.sha256(data).hexdigest()
    existing = (await db.execute(select(MediaAsset).where(MediaAsset.sha256 == sha).limit(1))).scalar_one_or_none()
    if existing:
        return existing  # 秒传去重

    now = datetime.now(timezone.utc)
    rel_dir = f"{category + '/' if category else ''}{now:%Y/%m}"
    base_dir = settings.media_path
    (base_dir / rel_dir).mkdir(parents=True, exist_ok=True)

    key = f"{rel_dir}/{uuid.uuid4().hex}{ext}"
    (base_dir / key).write_bytes(data)

    width = height = None
    thumb_key = None
    if kind == "image" and ext not in (".gif",):
        try:
            im = Image.open(io.BytesIO(data))
            width, height = im.size
            thumb_key = f"{rel_dir}/{uuid.uuid4().hex}-thumb.webp"
            t = im.convert("RGB")
            if t.width > THUMB_WIDTH:
                t = t.resize((THUMB_WIDTH, round(t.height * THUMB_WIDTH / t.width)), Image.LANCZOS)
            t.save(base_dir / thumb_key, "WEBP", quality=80)
        except Exception:
            width = height = None  # 探测失败不阻断上传

    asset = MediaAsset(filename=filename[:255], storage_key=key, kind=kind,
                       mime=mime or f"application/{kind}", size=len(data),
                       width=width, height=height, sha256=sha, thumb_key=thumb_key,
                       category=category, entries=entries)
    db.add(asset)
    await db.commit()
    return asset


async def set_category(db: AsyncSession, assets: list[MediaAsset], category: str) -> int:
    """只改分类标签：磁盘位置与 URL 都不动。

    分类是「整理视角」，不是存放位置 —— 换分类后正文里的 `/media/…` 仍然指向同一个
    文件，历史文章、RSS、外链分享都不会断。
    """
    changed = 0
    for a in assets:
        if a.category != category:
            a.category = category
            changed += 1
    await db.commit()
    return changed


def _clean_filename(name: str) -> str:
    """重命名只改展示名：去掉路径成分与控制字符，保留原扩展名。"""
    n = (name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    n = re.sub(r"[\x00-\x1f\x7f]", "", n).strip()
    return n[:255]


async def rename_asset(db: AsyncSession, asset: MediaAsset, filename: str) -> MediaAsset:
    """改展示名，`storage_key`/URL 不变。"""
    n = _clean_filename(filename)
    if not n:
        raise AppException(ErrorCode.BAD_REQUEST, "文件名不能为空")
    if n in (".", ".."):
        raise AppException(ErrorCode.BAD_REQUEST, "文件名不合法")
    asset.filename = n
    await db.commit()
    return asset


# 正文里引用素材的写法：`/media/blog/2026/11/<uuid>.png`（也可能是带域名的绝对地址）
_MEDIA_REF = re.compile(r"/media/([A-Za-z0-9._\-/]+)")


async def media_usage(db: AsyncSession) -> dict[int, list[dict]]:
    """asset_id → 引用它的内容列表（正文链接 / 封面 / 模型附件三处来源）。

    个人站内容量小，一次全表扫比给每张图单独查三张表更省往返；
    结果按内容 id 去重，同一篇里引用两次只算一条。
    """
    rows = (await db.execute(
        select(Content.id, Content.title, Content.type, Content.slug,
               Content.body_md, Content.cover_asset_id).order_by(Content.id))).all()
    keys = (await db.execute(select(MediaAsset.id, MediaAsset.storage_key))).all()
    by_key = {key: aid for aid, key in keys}

    usage: dict[int, dict[int, dict]] = {}

    def add(asset_id: int, brief: dict) -> None:
        usage.setdefault(asset_id, {})[brief["id"]] = brief

    briefs: dict[int, dict] = {}
    for cid, title, ctype, slug, body, cover_id in rows:
        brief = {"id": cid, "title": title, "type": ctype, "slug": slug}
        briefs[cid] = brief
        if cover_id:
            add(cover_id, brief)
        if body and "/media/" in body:
            for m in _MEDIA_REF.finditer(body):
                aid = by_key.get(m.group(1).rstrip("./"))
                if aid:
                    add(aid, brief)

    links = (await db.execute(
        select(content_media.c.content_id, content_media.c.asset_id))).all()
    for cid, aid in links:
        if cid in briefs:
            add(aid, briefs[cid])

    return {aid: list(v.values()) for aid, v in usage.items()}


async def referencing_contents(db: AsyncSession, asset: MediaAsset) -> list[dict]:
    """单张素材的引用方（删除前提示用，定向查询，不必全表扫）。"""
    found: dict[int, dict] = {}

    def add(cid: int, title: str, ctype: str, slug: str | None) -> None:
        found[cid] = {"id": cid, "title": title, "type": ctype, "slug": slug}

    for cid, title, ctype, slug in (await db.execute(
            select(Content.id, Content.title, Content.type, Content.slug)
            .where(Content.cover_asset_id == asset.id))).all():
        add(cid, title, ctype, slug)
    for cid, title, ctype, slug in (await db.execute(
            select(Content.id, Content.title, Content.type, Content.slug)
            .where(Content.body_md.contains(f"/media/{asset.storage_key}")))).all():
        add(cid, title, ctype, slug)
    for cid, title, ctype, slug in (await db.execute(
            select(Content.id, Content.title, Content.type, Content.slug)
            .join(content_media, content_media.c.content_id == Content.id)
            .where(content_media.c.asset_id == asset.id))).all():
        add(cid, title, ctype, slug)
    return list(found.values())


def asset_public(a: MediaAsset) -> dict:
    return {"id": a.id, "filename": a.filename, "url": f"/media/{a.storage_key}", "kind": a.kind, "mime": a.mime,
            "size": a.size, "width": a.width, "height": a.height,
            "thumb": (f"/media/{a.thumb_key}" if a.thumb_key else None),
            "storage_key": a.storage_key, "category": a.category, "uploaded_at": a.uploaded_at,
            "entries": a.entries}


async def assert_deletable(db: AsyncSession, asset: MediaAsset) -> None:
    refs = await referencing_contents(db, asset)
    if refs:
        names = "、".join(f"《{r['title']}》" for r in refs[:3])
        more = f" 等 {len(refs)} 篇" if len(refs) > 3 else ""
        raise AppException(ErrorCode.CONFLICT, f"素材仍被 {names}{more} 引用",
                           data={"content_ids": [r["id"] for r in refs], "contents": refs})
