from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, TZDateTime, utcnow


class ViewEvent(Base):
    """原始采集事件，30 天后由聚合任务清理。"""
    __tablename__ = "view_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[int] = mapped_column(Integer, index=True)      # YYYYMMDD
    path: Mapped[str] = mapped_column(String(255))
    content_id: Mapped[int | None] = mapped_column(ForeignKey("contents.id"), default=None, index=True)
    referrer: Mapped[str] = mapped_column(String(255), default="")
    ip_hash: Mapped[str] = mapped_column(String(64))
    ua_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class StatsDaily(Base):
    __tablename__ = "stats_daily"

    day: Mapped[int] = mapped_column(Integer, primary_key=True)
    pv: Mapped[int] = mapped_column(Integer, default=0)
    uv: Mapped[int] = mapped_column(Integer, default=0)


class StatsContent(Base):
    __tablename__ = "stats_content"

    day: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"), primary_key=True)
    pv: Mapped[int] = mapped_column(Integer, default=0)
    uv: Mapped[int] = mapped_column(Integer, default=0)


class PushLog(Base):
    __tablename__ = "push_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    urls_json: Mapped[str] = mapped_column(String(4000), default="[]")
    result_json: Mapped[str] = mapped_column(String(4000), default="{}")
    triggered_by: Mapped[str] = mapped_column(String(16), default="publish")  # publish | manual
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class PendingPush(Base):
    """百度 token 未配置期间的待推 URL（配置后 SEO 面板批量补推）。"""
    __tablename__ = "pending_push"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    content_id: Mapped[int | None] = mapped_column(ForeignKey("contents.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class PushedUrl(Base):
    """已成功推送过的地址：同一 URL 只主动推一次，避免重复推送浪费配额。

    只在「整批全部成功」时写入 —— 百度只回 success 计数，部分成功时无法判断是哪几条
    失败，宁可留到下次重推（百度侧会去重），也不要把没推上去的记成已推。
    """
    __tablename__ = "pushed_urls"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    first_pushed_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    last_pushed_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    push_count: Mapped[int] = mapped_column(Integer, default=1)


class RebuildJob(Base):
    __tablename__ = "rebuild_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|failed|skipped
    log: Mapped[str] = mapped_column(String(4000), default="")
    triggered_by: Mapped[str] = mapped_column(String(16), default="publish")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
