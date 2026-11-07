from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, TZDateTime, utcnow


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))          # 原始文件名（仅展示用）
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)  # YYYY/MM/uuid.ext
    kind: Mapped[str] = mapped_column(String(16))               # image | model3d | video | file
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    thumb_key: Mapped[str | None] = mapped_column(String(255), default=None)  # webp 缩略图
    category: Mapped[str | None] = mapped_column(String(16), default=None, index=True)  # blog|avatar|render|model；None=未分类
    # 模型压缩包内容清单 [{"path": "tex/wood.png", "size": 12345}]，上传时读 zip 中央目录得到
    entries: Mapped[list | None] = mapped_column(JSON, default=None)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True)
    uploaded_by: Mapped["User | None"] = relationship(lazy="selectin")   # noqa: F821
    uploaded_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
