from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, TZDateTime, utcnow


class SiteSetting(Base):
    """分组 KV：key 形如 'profile.nickname' / 'site.title' / 'nav.items'。"""
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON, default=None)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
