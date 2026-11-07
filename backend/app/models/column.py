"""栏目：文章的单归属分组（一篇内容最多属于一个栏目）。

与标签同款隔离规则：栏目按内容类型（article/model/chat）各自独立一套，
同名可跨类型共存；前台在对应列表页左侧以目录栏形式呈现。
"""
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, TZDateTime, utcnow


class Column(Base):
    __tablename__ = "columns"
    __table_args__ = (
        sa.UniqueConstraint("type", "name", name="uq_columns_type_name"),
        sa.UniqueConstraint("type", "slug", name="uq_columns_type_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64))
    slug: Mapped[str] = mapped_column(sa.String(128))
    type: Mapped[str] = mapped_column(sa.String(16), default="article")  # article | model | chat
    summary: Mapped[str] = mapped_column(sa.Text, default="")
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0)
    # 层级树：最多 3 级（根=1 级），应用层校验父级同类型/深度/防环
    parent_id: Mapped[int | None] = mapped_column(sa.ForeignKey("columns.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)

    contents: Mapped[list["Content"]] = relationship(  # noqa: F821
        back_populates="column", foreign_keys="Content.column_id")
