"""监控看板查询（docs/api-reference.md §7）。"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import Content, MediaAsset, StatsContent, StatsDaily, ViewEvent


def _days_ago(n: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y%m%d"))


async def overview(db: AsyncSession) -> dict:
    today = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
    yday = _days_ago(1)

    async def day_stat(d: int):
        row = (await db.execute(select(StatsDaily).where(StatsDaily.day == d))).scalar_one_or_none()
        return {"pv": row.pv if row else 0, "uv": row.uv if row else 0}

    counts = (await db.execute(
        select(Content.type, func.count()).where(Content.status == "published").group_by(Content.type))).all()
    storage = (await db.execute(select(func.coalesce(func.sum(MediaAsset.size), 0),
                                       func.count(MediaAsset.id)))).one()
    return {"today": await day_stat(today), "yesterday": await day_stat(yday),
            "total_published": {t: int(c) for t, c in counts},
            "storage_used": int(storage[0]), "media_count": int(storage[1])}


async def trend(db: AsyncSession, start: int, end: int) -> list[dict]:
    rows = (await db.execute(
        select(StatsDaily).where(StatsDaily.day >= start, StatsDaily.day <= end)
        .order_by(StatsDaily.day))).scalars().all()
    have = {r.day: r for r in rows}
    out = []
    d0 = datetime.strptime(str(start), "%Y%m%d").date()
    d1 = datetime.strptime(str(end), "%Y%m%d").date()
    cur = d0
    while cur <= d1:
        k = int(cur.strftime("%Y%m%d"))
        r = have.get(k)
        out.append({"day": str(k), "pv": r.pv if r else 0, "uv": r.uv if r else 0})
        cur += timedelta(days=1)
    return out


async def top_content(db: AsyncSession, start: int, end: int, limit: int,
                      type_: str | None) -> list[dict]:
    q = (select(StatsContent.content_id, func.sum(StatsContent.pv).label("pv"),
                func.sum(StatsContent.uv).label("uv"))
         .where(StatsContent.day >= start, StatsContent.day <= end)
         .group_by(StatsContent.content_id).order_by(func.sum(StatsContent.pv).desc())
         .limit(limit))
    rows = (await db.execute(q)).all()
    ids = [r[0] for r in rows]
    contents = {}
    if ids:
        cs = (await db.execute(select(Content).where(Content.id.in_(ids)))).scalars().all()
        contents = {c.id: c for c in cs}
    out = [{"content_id": cid, "title": contents.get(cid).title if cid in contents else "?",
            "type": contents[cid].type if cid in contents else "?", "pv": int(pv), "uv": int(uv)}
           for cid, pv, uv in rows if cid in contents]
    if type_:
        out = [x for x in out if x["type"] == type_]
    return out


async def content_detail(db: AsyncSession, cid: int, start: int, end: int) -> dict:
    days = (await db.execute(
        select(StatsContent).where(StatsContent.content_id == cid,
                                   StatsContent.day >= start, StatsContent.day <= end)
        .order_by(StatsContent.day))).scalars().all()
    srcs = (await db.execute(
        select(ViewEvent.referrer, func.count())
        .where(ViewEvent.content_id == cid, ViewEvent.day >= start, ViewEvent.day <= end)
        .group_by(ViewEvent.referrer).order_by(func.count().desc()).limit(20))).all()
    # 与 trend 同：按区间补零成连续日期，否则无数据的天不出现，前端 7/30 天切片无法区分
    have = {d.day: d for d in days}
    out = []
    cur = datetime.strptime(str(start), "%Y%m%d").date()
    d1 = datetime.strptime(str(end), "%Y%m%d").date()
    while cur <= d1:
        k = int(cur.strftime("%Y%m%d"))
        r = have.get(k)
        out.append({"day": str(k), "pv": r.pv if r else 0, "uv": r.uv if r else 0})
        cur += timedelta(days=1)
    return {"days": out,
            "sources": [{"referrer": r or "", "pv": int(c)} for r, c in srcs]}


SEARCH_DOMAINS = ("baidu.", "bing.", "google.", "so.com", "sogou.", "sm.cn", "yandex.", "duckduckgo.")
SOCIAL_DOMAINS = ("weibo.", "zhihu.", "juejin.", "bilibili.", "v2ex.", "t.co", "twitter.", "weixin.")


def own_hosts() -> set[str]:
    """本站 host 加它的 www / 去 www 变体：裸域与 www 是两个入口，都算自站。"""
    h = urlparse(settings.site_url).netloc.lower()
    if not h:
        return set()
    return {h, h[4:] if h.startswith("www.") else f"www.{h}"}


def classify_referrer(ref: str) -> str:
    if not ref:
        return "direct"
    r = ref.lower()
    # 站内自跳（列表→详情、详情→关于页）不是外部来源。以前它落进「其他」，
    # 于是那一栏几乎全是自家流量，等于没有信息；host 精确比对，不做后缀匹配。
    if urlparse(r).netloc.lower() in own_hosts():
        return "direct"
    if any(d in r for d in SEARCH_DOMAINS):
        return "search"
    if any(d in r for d in SOCIAL_DOMAINS):
        return "social"
    return "other"


async def sources(db: AsyncSession, start: int, end: int) -> dict:
    rows = (await db.execute(
        select(ViewEvent.referrer, func.count())
        .where(ViewEvent.day >= start, ViewEvent.day <= end)
        .group_by(ViewEvent.referrer).order_by(func.count().desc()))).all()
    buckets = {"direct": 0, "search": 0, "social": 0, "other": 0}
    items = []
    for ref, cnt in rows:
        b = classify_referrer(ref)
        buckets[b] += int(cnt)
        if len(items) < 15 and ref:
            items.append({"referrer": ref, "pv": int(cnt)})
    return {"items": items, **{k: v for k, v in buckets.items()}}


async def export_rows(db: AsyncSession, start: int, end: int) -> list[tuple]:
    daily = (await db.execute(
        select(StatsDaily).where(StatsDaily.day >= start, StatsDaily.day <= end)
        .order_by(StatsDaily.day))).scalars().all()
    contents = (await db.execute(
        select(StatsContent.content_id, func.sum(StatsContent.pv), func.sum(StatsContent.uv))
        .where(StatsContent.day >= start, StatsContent.day <= end)
        .group_by(StatsContent.content_id))).all()
    cmap = dict((await db.execute(select(Content.id, Content.title))).all())
    rows: list[tuple] = [("section", "key", "pv", "uv")]
    rows += [("daily", str(d.day), str(d.pv), str(d.uv)) for d in daily]
    rows += [("", "", "", "")]
    rows += [("content", f"{cid} {cmap.get(cid, '?')}", str(int(pv)), str(int(uv)))
             for cid, pv, uv in contents]
    return rows
