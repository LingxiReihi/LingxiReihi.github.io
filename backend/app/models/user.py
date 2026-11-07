from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, TZDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    nickname: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str | None] = mapped_column(String(120), unique=True, default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(255), default=None)
    signature: Mapped[str] = mapped_column(String(200), default="")
    bio_md: Mapped[str] = mapped_column(Text, default="")
    # 社交链 [{label,url}]；技能/经历只渲染 super 那一份（About 页）
    social_links: Mapped[list | None] = mapped_column(JSON, default=None)
    skills: Mapped[list | None] = mapped_column(JSON, default=None)
    experience: Mapped[list | None] = mapped_column(JSON, default=None)
    role: Mapped[str] = mapped_column(String(16), default="staff")   # super | staff
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(128), default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    @property
    def is_super(self) -> bool:
        return self.role == "super"
