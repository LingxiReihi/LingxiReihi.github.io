"""推送去重：同一 URL 只主动推一次，只有显式 force 才重推。"""
import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import PendingPush, PushedUrl
from app.services import seo_push

U1 = "https://example.com/blog/post-one"
U2 = "https://example.com/blog/post-two"
U3 = "https://example.com/models/thing"


@pytest.fixture
def push_on(monkeypatch):
    monkeypatch.setattr(settings, "baidu_push_api", "https://push.example.com/api")
    monkeypatch.setattr(settings, "seo_push_enabled", True)


def _transport(sent: list[str], success_of=None):
    """记录实际发出去的 URL；success_of 可让响应只报部分成功。"""
    def handler(req: httpx.Request) -> httpx.Response:
        batch = [u for u in req.content.decode().split("\n") if u]
        sent.extend(batch)
        n = success_of(batch) if success_of else len(batch)
        return httpx.Response(200, json={"success": n, "remain": 0})
    return httpx.MockTransport(handler)


async def _pushed() -> dict[str, int]:
    async with SessionLocal() as db:
        rows = (await db.execute(select(PushedUrl))).scalars().all()
        return {r.url: r.push_count for r in rows}


async def test_first_push_records_then_second_skips(push_on):
    sent: list[str] = []
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, [U1, U2], transport=_transport(sent))
    assert (r["success"], r["already"]) == (2, 0)
    assert sent == [U1, U2]
    assert await _pushed() == {U1: 1, U2: 1}

    # 再推同一批：一条都不发
    sent.clear()
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, [U1, U2], transport=_transport(sent))
    assert (r["success"], r["already"]) == (0, 2)
    assert sent == []
    assert "均已推送过" in r["notice"][0]

    # 新旧混合：只发新的那条
    sent.clear()
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, [U1, U3], transport=_transport(sent))
    assert (r["success"], r["already"]) == (1, 1)
    assert sent == [U3]


async def test_force_repushes_and_counts(push_on):
    sent: list[str] = []
    async with SessionLocal() as db:
        await seo_push.push_urls(db, [U1], transport=_transport(sent))
    sent.clear()
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, [U1], force=True, transport=_transport(sent))
    assert (r["success"], r["already"]) == (1, 0)
    assert sent == [U1]
    assert await _pushed() == {U1: 2}


async def test_partial_success_is_not_recorded(push_on):
    """百度只回总数，部分成功时无法判断哪几条失败 → 不记账，下次重推。"""
    sent: list[str] = []
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, [U1, U2], transport=_transport(sent, success_of=lambda b: 1))
    assert r["success"] == 1 and r["fail"] == 1
    assert await _pushed() == {}

    sent.clear()
    async with SessionLocal() as db:
        await seo_push.push_urls(db, [U1, U2], transport=_transport(sent))
    assert sent == [U1, U2]          # 两条都重推（百度侧去重）


async def test_sentinel_and_blank_ignored(push_on):
    sent: list[str] = []
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, ["__sitemap__", "", U1], transport=_transport(sent))
    assert sent == [U1] and r["success"] == 1
    assert await _pushed() == {U1: 1}       # 哨兵不会被记成已推


async def test_token_missing_goes_to_pending_without_recording(monkeypatch):
    monkeypatch.setattr(settings, "baidu_push_api", "")
    monkeypatch.setattr(settings, "seo_push_enabled", False)
    async with SessionLocal() as db:
        r = await seo_push.push_urls(db, [U1, U2])
    assert r["skipped"] == 2 and r["already"] == 0
    assert await _pushed() == {}
    async with SessionLocal() as db:
        pend = (await db.execute(select(PendingPush))).scalars().all()
    assert {p.url for p in pend} == {U1, U2}


async def test_pending_dup_still_skipped_on_push(push_on):
    """待推队列里混进已推过的地址：补推时也要跳过。"""
    async with SessionLocal() as db:
        await seo_push.push_urls(db, [U1], transport=_transport([]))
        db.add(PendingPush(url=U1))
        db.add(PendingPush(url=U2))
        await db.commit()

    async with SessionLocal() as db:
        rows = await seo_push.pending_urls(db)
        await seo_push.clear_pending(db, rows)
        sent: list[str] = []
        r = await seo_push.push_urls(db, [p.url for p in rows], transport=_transport(sent))
    assert sent == [U2] and r["already"] == 1
