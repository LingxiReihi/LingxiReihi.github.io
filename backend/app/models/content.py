from datetime import datetime

from sqlalchemy import (JSON, Column, ForeignKey, Index, Integer, String,
                        Table, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, TZDateTime, utcnow

content_tags = Table(
    "content_tags", Base.metadata,
    Column("content_id", ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

content_media = Table(
    "content_media", Base.metadata,
    Column("content_id", ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True),
    Column("asset_id", ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True),
    Column("sort_order", Integer, default=0),
)


class Content(Base):
    __tablename__ = "contents"
    __table_args__ = (
        Index("ix_contents_type_status_pub", "type", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(16))          # article | model | chat
    status: Mapped[str] = mapped_column(String(16), default="draft")
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str | None] = mapped_column(String(200), unique=True, default=None)
    summary: Mapped[str] = mapped_column(Text, default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    cover_asset_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"), default=None)
    media_kind: Mapped[str | None] = mapped_column(String(16), default=None)  # 3d | render | animation
    extra: Mapped[dict | None] = mapped_column(JSON, default=None)
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    downloads: Mapped[int] = mapped_column(Integer, default=0)  # 模型文件被下载次数
    likes: Mapped[int] = mapped_column(Integer, default=0)
    column_id: Mapped[int | None] = mapped_column(ForeignKey("columns.id"), default=None)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True)

    created_by: Mapped["User | None"] = relationship(lazy="selectin")   # noqa: F821

    tags: Mapped[list["Tag"]] = relationship(secondary=content_tags, back_populates="contents", lazy="selectin")
    assets: Mapped[list["MediaAsset"]] = relationship(secondary=content_media, lazy="selectin",
                                                      order_by="content_media.c.sort_order")
    cover_asset: Mapped["MediaAsset | None"] = relationship(foreign_keys=[cover_asset_id], lazy="selectin")
    column: Mapped["Column | None"] = relationship(back_populates="contents", lazy="selectin")  # noqa: F821


class Tag(Base):
    __tablename__ = "tags"
    # 标签按内容类型隔离：article/model/chat 各自独立一套，同名可跨类型共存
    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_tags_type_name"),
        UniqueConstraint("type", "slug", name="uq_tags_type_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16), default="article")  # article | model | chat

    contents: Mapped[list[Content]] = relationship(secondary=content_tags, back_populates="tags")
