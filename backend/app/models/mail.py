from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, TZDateTime, utcnow


class MailQueue(Base):
    """出站发信队列：额度、退避、重试全部从这张表推导，所以重启不失效、也天然可查。

    状态只有三种：pending（待发，含等待重试）| sent | dropped（重试次数用尽）。
    「最近失败」不是独立状态，而是 pending 且 attempts>0 且 updated_at 在窗口内 ——
    这样行始终只有一处真相，不会出现"failed 但其实还会再发"的歧义。

    ⚠ pending 期间正文是明文入库：只放评论通知这类内容不敏感的信；
    带明文口令的重置邮件走直发路径，绝不进这里（否则口令要在库里躺到下一小时）。
    """
    __tablename__ = "mail_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_addr: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(200))
    body_text: Mapped[str] = mapped_column(Text)
    # HTML 正文（由 Markdown 渲染）。空串 = 这封信只有纯文本
    body_html: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(24), default="notify")   # comment_author | comment_visitor
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(200), default="")
    comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="SET NULL"), default=None)
    next_try_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_mail_queue_status_next", "status", "next_try_at"),)
