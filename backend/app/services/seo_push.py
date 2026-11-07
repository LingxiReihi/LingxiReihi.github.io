"""百度主动推送客户端。token 未配置 => URL 入 pending_push，配置后 SEO 面板批量补推。

去重规则：`pushed_urls` 记录已经成功推送过的地址，同一 URL 默认不再重复推送
（重新发布、手动批量补推都不会重复消耗配额）。确实需要重推时显式传 `force=True`。
"""
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import PendingPush, PushLog, PushedUrl


def _clean(urls: list[str]) -> list[str]:
    """去重保序、丢掉空值与非 http 的哨兵值（如重建用的 `__sitemap__`）。"""
    return [u for u in dict.fromkeys(urls) if u and u.startswith("http")]


async def already_pushed(db: AsyncSession, urls: list[str]) -> set[str]:
    if not urls:
        return set()
    rows = await db.execute(select(PushedUrl.url).where(PushedUrl.url.in_(urls)))
    return set(rows.scalars().all())


async def _mark_pushed(db: AsyncSession, urls: list[str]) -> None:
    """写入/更新推送记录（不提交，与 PushLog 一起提交）。"""
    if not urls:
        return
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(PushedUrl).where(PushedUrl.url.in_(urls)))).scalars().all()
    existing = {r.url: r for r in rows}
    for u in urls:
        row = existing.get(u)
        if row is not None:
            row.last_pushed_at = now
            row.push_count = (row.push_count or 0) + 1
        else:
            db.add(PushedUrl(url=u, first_pushed_at=now, last_pushed_at=now, push_count=1))


async def push_urls(db: AsyncSession, urls: list[str], triggered_by: str = "manual", *,
                    force: bool = False,
                    transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """推送一批 URL。默认过滤掉已推送过的，返回值里的 `already` 是被跳过的条数。"""
    urls = _clean(urls)
    already = 0
    if urls and not force:
        done = await already_pushed(db, urls)
        if done:
            already = len(done)
            urls = [u for u in urls if u not in done]
    if not urls:
        notice = ["全部 URL 均已推送过，跳过"] if already else []
        return {"success": 0, "fail": 0, "skipped": 0, "already": already,
                "notice": notice, "remaining": None}

    if not (settings.baidu_push_api and settings.seo_push_enabled):
        for u in urls:
            db.add(PendingPush(url=u))
        db.add(PushLog(urls_json=json.dumps(urls)[:4000],
                       result_json=json.dumps({"status": "pending", "reason": "token 未配置"}),
                       triggered_by=triggered_by))
        await db.commit()
        return {"success": 0, "fail": 0, "skipped": len(urls), "already": already,
                "notice": ["token 未配置，已入待推队列"], "remaining": None}

    async with httpx.AsyncClient(timeout=15, transport=transport) as client:
        r = await client.post(settings.baidu_push_api,
                              content="\n".join(urls).encode(),
                              headers={"Content-Type": "text/plain"})
    body = r.json() if r.status_code == 200 else {"error": r.status_code, "text": r.text[:200]}
    success = int(body.get("success", 0) or 0) if r.status_code == 200 else 0
    # 只有整批都成功才记账：百度只回总数，部分成功时无法判断哪几条失败，
    # 宁可让它们下次重推（百度侧会去重），也不要把没推上去的记成已推。
    if success == len(urls):
        await _mark_pushed(db, urls)
    db.add(PushLog(urls_json=json.dumps(urls)[:4000],
                   result_json=json.dumps(body)[:4000], triggered_by=triggered_by))
    await db.commit()
    return {"success": success, "fail": len(urls) - success, "skipped": 0, "already": already,
            "notice": body.get("notice", []) or body.get("error", []),
            "remaining": body.get("remaining")}


async def pending_urls(db: AsyncSession, limit: int = 500) -> list[PendingPush]:
    return list((await db.execute(select(PendingPush).limit(limit))).scalars().all())


async def clear_pending(db: AsyncSession, rows: list[PendingPush]) -> None:
    for r in rows:
        await db.delete(r)
    await db.commit()
