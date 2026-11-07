"""日聚合：view_events -> stats_daily / stats_content + contents.view_count 回填。
启动 asyncio 循环（每 30 分钟重算今日+昨日，幂等 upsert）；亦可 CLI 调用。"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import SessionLocal
from ..models import Content, StatsContent, StatsDaily, ViewEvent

log = logging.getLogger("aggregate")


def _today() -> int:
    return int(datetime.now(timezone.utc).strftime("%Y%m%d"))


async def run_aggregate(db: AsyncSession, day: int) -> None:
    rows = (await db.execute(
        select(func.count(ViewEvent.id), func.count(func.distinct(ViewEvent.ip_hash + ViewEvent.ua_hash)))
        .where(ViewEvent.day == day))).one()
    pv, uv = int(rows[0] or 0), int(rows[1] or 0)
    stmt = sqlite_insert(StatsDaily).values(day=day, pv=pv, uv=uv)
    await db.execute(stmt.on_conflict_do_update(index_elements=["day"], set_={"pv": pv, "uv": uv}))

    per = (await db.execute(
        select(ViewEvent.content_id, func.count(ViewEvent.id),
               func.count(func.distinct(ViewEvent.ip_hash + ViewEvent.ua_hash)))
        .where(ViewEvent.day == day, ViewEvent.content_id.is_not(None))
        .group_by(ViewEvent.content_id))).all()
    for cid, cpv, cuv in per:
        stmt = sqlite_insert(StatsContent).values(day=day, content_id=cid, pv=int(cpv), uv=int(cuv))
        await db.execute(stmt.on_conflict_do_update(index_elements=["day", "content_id"],
                                                    set_={"pv": int(cpv), "uv": int(cuv)}))
    # 回填累计 view_count
    ids = [cid for cid, _, _ in per]
    if ids:
        totals = (await db.execute(
            select(ViewEvent.content_id, func.count(ViewEvent.id))
            .where(ViewEvent.content_id.in_(ids)).group_by(ViewEvent.content_id))).all()
        for cid, total in totals:
            await db.execute(Content.__table__.update().where(Content.id == cid)
                             .values(view_count=int(total)))
    await db.commit()


async def aggregate_loop() -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            days = {int(now.strftime("%Y%m%d")), int((now - __import__("datetime").timedelta(days=1)).strftime("%Y%m%d"))}
            async with SessionLocal() as db:
                for d in days:  # 幂等 upsert，重算今日+昨日即可跨月正确
                    await run_aggregate(db, d)
        except Exception:
            log.exception("aggregate failed")
        await asyncio.sleep(1800)
