from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, TZDateTime, utcnow


class Comment(Base):
    """先审后显评论：邮箱仅后台可见，前台以 md5(email) 映射到本地开源图包出头像。"""
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(120))          # 不明文外发，仅后台展示
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    submit_ip: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    # 首次审核通过时给评论者发过通知的时间；NULL = 没发过。
    # 去重靠这一列而不是靠"队列里有没有行"，所以「通过→拒绝→再通过」也只发一封。
    notified_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None)
