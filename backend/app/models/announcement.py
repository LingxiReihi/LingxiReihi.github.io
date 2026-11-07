from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, TZDateTime, utcnow


class Announcement(Base):
    """更新公告：本期由后台「登录弹窗 + 独立管理页」消费；status/published_at 仍为前台预留。"""
    __tablename__ = "announcements"
    __table_args__ = (Index("ix_announcements_status_pub", "status", "published_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="published")   # draft | published
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True)

    created_by: Mapped["User | None"] = relationship(lazy="selectin")  # noqa: F821


class AnnouncementRead(Base):
    """逐条已读水位（v2 登录弹窗用）。复合 PK 天然去重；两侧 CASCADE——
    删公告不留悬空已读行，删用户同理，因此「未读数」永不需要脏数据兜底。"""
    __tablename__ = "announcement_reads"
    __table_args__ = (Index("ix_announcement_reads_user", "user_id"),)

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
