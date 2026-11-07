"""公开 DTO（字段白名单，仅 published 内容使用；docs/backend-architecture.md §5）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    type: str = "article"


class ColumnBrief(BaseModel):
    id: int
    name: str
    slug: str
    type: str = "article"


def _asset_url(asset) -> str | None:
    return f"/media/{asset.storage_key}" if asset else None


def _asset_full(asset) -> dict:
    return {
        "id": asset.id, "url": f"/media/{asset.storage_key}", "kind": asset.kind,
        "mime": asset.mime, "size": asset.size, "width": asset.width, "height": asset.height,
        "thumb": (f"/media/{asset.thumb_key}" if asset.thumb_key else None),
        # 前台要按扩展名分发渲染器、并按 zip 清单展示层级，故带上文件名与包内容
        "filename": asset.filename, "storage_key": asset.storage_key, "entries": asset.entries,
    }


class ContentOut(BaseModel):
    """列表卡片级 DTO。"""
    id: int
    type: str
    title: str
    slug: str | None
    summary: str
    cover: str | None
    tags: list[TagOut]
    published_at: datetime | None
    view_count: int
    likes: int = 0
    media_kind: str | None = None
    extra: dict = {}
    column: ColumnBrief | None = None

    @classmethod
    def from_content(cls, c, extra_public_keys=("reading_time",)) -> "ContentOut":
        allowed = (c.extra or {}).keys() if extra_public_keys is None else extra_public_keys
        extra = {k: c.extra[k] for k in (c.extra or {}) if k in allowed}
        return cls(id=c.id, type=c.type, title=c.title, slug=c.slug, summary=c.summary,
                   cover=_asset_url(c.cover_asset), tags=[TagOut.model_validate(t) for t in c.tags],
                   published_at=c.published_at, view_count=c.view_count, likes=c.likes,
                   media_kind=c.media_kind, extra=extra,
                   column=ColumnBrief(id=c.column.id, name=c.column.name, slug=c.column.slug)
                   if getattr(c, "column", None) else None)


class HotOut(ContentOut):
    """热门位 DTO：多带已过审评论数与热度分（分数由后端算，前台只拿来画条，别抄一份权重）。"""
    comment_count: int = 0
    score: int = 0

    @classmethod
    def from_row(cls, c, comment_count: int, score: int) -> "HotOut":
        return cls(**ContentOut.from_content(c).model_dump(),
                   comment_count=comment_count, score=score)


class ContentDetail(ContentOut):
    """详情 DTO：含 body_md / assets / 完整 extra / prev / next / related。"""
    body_md: str
    assets: list[dict] = []
    prev: dict | None = None
    next: dict | None = None
    related: list[ContentOut] = []
    # 详情页规格表用：最近更新与下载次数（列表卡片不下发，省体积）
    updated_at: datetime | None = None
    downloads: int = 0
    # 作者署名：白名单只有 nickname/avatar（email、username、role 一律不下发）
    author: dict = {}

    @classmethod
    def from_content_full(cls, c, author: dict | None = None) -> "ContentDetail":
        base = ContentOut.from_content(c, extra_public_keys=None)  # type: ignore[arg-type]
        d = cls(**{**base.model_dump(), "body_md": c.body_md,
                   "assets": [_asset_full(a) for a in c.assets],
                   "updated_at": c.updated_at, "downloads": c.downloads,
                   "author": author or {},
                   "extra": c.extra or {}})
        return d
