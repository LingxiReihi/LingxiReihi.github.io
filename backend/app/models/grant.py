from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, TZDateTime, utcnow


class AdminGrant(Base):
    """一条 = 一个权限点 + 一个作用域。super 不落库（判定走 is_super 短路）。"""
    __tablename__ = "admin_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "permission", "scope_type", "scope_id", name="uq_admin_grant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    permission: Mapped[str] = mapped_column(String(32))
    scope_type: Mapped[str] = mapped_column(String(16), default="global")   # global | column
    scope_id: Mapped[int | None] = mapped_column(Integer, default=None)     # scope_type=column → columns.id
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
