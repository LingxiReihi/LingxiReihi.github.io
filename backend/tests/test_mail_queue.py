"""出站发信队列：额度、退避、重试都从表本身推导（重启不失效，也天然可查）。

不变式：
- 额度满/退避中 → 什么都不发，也不改任何行（不是丢弃，是延后）；
- 通道未配置 → 静默延后，绝不烧 attempts、不触发退避（那是站点没开通知，不是发信失败）；
- 只有真的尝试发出去并失败才算一次失败。
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal, utcnow
from app.models import MailQueue
from app.services import mail_queue, mail_sender


@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    """conftest 把 MAIL_* env 清空了；这里声明「通道可用」，让测试测的是队列而非配置。"""
    monkeypatch.setattr(mail_sender, "channel_ready", lambda cfg: True)
    calls: list[dict] = []

    async def fake(db, *, to, subject, body_text, body_html="", transport=None):
        calls.append({"to": to, "subject": subject, "body_text": body_text})

    monkeypatch.setattr(mail_sender, "send", fake)
    return calls


async def _rows(status: str | None = None) -> list[MailQueue]:
    async with SessionLocal() as db:
        q = select(MailQueue).order_by(MailQueue.id)
        if status:
            q = q.where(MailQueue.status == status)
        return list((await db.execute(q)).scalars().all())


async def _enqueue(to: str = "a@x.test", n: int = 1):
    async with SessionLocal() as db:
        for i in range(n):
            await mail_queue.enqueue(db, to=to, subject=f"标题 {i}", body_text=f"正文 {i}",
                                     kind="test")
        await db.commit()


async def test_enqueue_then_drain_marks_sent():
    await _enqueue()
    async with SessionLocal() as db:
        stats = await mail_queue.drain(db)
    assert stats == {"sent": 1, "failed": 0, "dropped": 0, "deferred": 0}
    assert (await _rows("sent"))[0].to_addr == "a@x.test"


async def test_drain_sends_in_order_with_stored_text(_ready):
    await _enqueue(n=3)
    async with SessionLocal() as db:
        await mail_queue.drain(db)
    assert [c["to"] for c in _ready] == ["a@x.test"] * 3
    assert _ready[0]["subject"] == "标题 0" and _ready[0]["body_text"] == "正文 0"


async def test_hourly_budget_defers_the_rest(monkeypatch):
    monkeypatch.setattr(mail_queue, "HOURLY_LIMIT", 2)
    await _enqueue(n=5)
    async with SessionLocal() as db:
        stats = await mail_queue.drain(db)
    assert stats["sent"] == 2 and stats["deferred"] == 3
    assert len(await _rows("pending")) == 3          # 延后不是丢弃：行还在，状态没动


async def test_failure_defers_one_hour_and_bumps_attempts(monkeypatch):
    async def boom(db, **kw):
        raise mail_sender.MailError("对端拒收")

    monkeypatch.setattr(mail_sender, "send", boom)
    await _enqueue()
    async with SessionLocal() as db:
        stats = await mail_queue.drain(db)
    row = (await _rows("pending"))[0]
    assert stats == {"sent": 0, "failed": 1, "dropped": 0, "deferred": 0}
    assert row.attempts == 1 and "拒收" in row.last_error
    assert row.next_try_at > utcnow() + timedelta(minutes=50)


async def test_dropped_after_five_attempts(monkeypatch):
    async def boom(db, **kw):
        raise mail_sender.MailError("一直失败")

    monkeypatch.setattr(mail_sender, "send", boom)
    monkeypatch.setattr(mail_queue, "BACKOFF_FAILS", 99)    # 本例只测次数上限，别被退避拦下
    await _enqueue()
    for _ in range(5):
        async with SessionLocal() as db:
            rows = (await db.execute(select(MailQueue))).scalars().all()
            for r in rows:
                r.next_try_at = utcnow() - timedelta(minutes=1)   # 越过重试等待，只为测次数上限
            await db.commit()
            await mail_queue.drain(db)
    assert await _rows("pending") == []
    assert (await _rows("dropped"))[0].attempts == 5


async def test_backoff_pauses_whole_queue(monkeypatch):
    async def boom(db, **kw):
        raise mail_sender.MailError("连不上")

    monkeypatch.setattr(mail_sender, "send", boom)
    monkeypatch.setattr(mail_queue, "MAX_ATTEMPTS", 99)     # 别在退避测试里提前 dropped
    await _enqueue(n=3)
    for _ in range(3):
        async with SessionLocal() as db:
            await mail_queue.drain(db)                      # 三次都失败 → 触发退避
    await _enqueue(to="later@x.test")
    async with SessionLocal() as db:
        stats = await mail_queue.drain(db)
    assert stats["sent"] == 0                               # 暂停期间新信也不发
    assert len(await _rows("pending")) == 4                 # 但一行都没丢


async def test_backoff_releases_after_window(monkeypatch):
    async def boom(db, **kw):
        raise mail_sender.MailError("连不上")

    monkeypatch.setattr(mail_sender, "send", boom)
    monkeypatch.setattr(mail_queue, "MAX_ATTEMPTS", 99)
    await _enqueue(n=3)
    for _ in range(3):
        async with SessionLocal() as db:
            await mail_queue.drain(db)
    async with SessionLocal() as db:                        # 把失败记录推到窗口外
        for r in (await db.execute(select(MailQueue))).scalars().all():
            r.updated_at = utcnow() - timedelta(minutes=45)
            r.next_try_at = utcnow() - timedelta(minutes=45)
        await db.commit()

    async def ok(db, **kw):
        return None
    monkeypatch.setattr(mail_sender, "send", ok)
    async with SessionLocal() as db:
        stats = await mail_queue.drain(db)
    assert stats["sent"] == 3                               # 恢复后积压照常补发


async def test_unconfigured_channel_defers_without_burning_attempts(monkeypatch):
    monkeypatch.setattr(mail_sender, "channel_ready", lambda cfg: False)
    await _enqueue(n=2)
    async with SessionLocal() as db:
        stats = await mail_queue.drain(db)
    rows = await _rows("pending")
    assert stats == {"sent": 0, "failed": 0, "dropped": 0, "deferred": 2}
    assert all(r.attempts == 0 for r in rows)               # 站点没开通知 ≠ 发信失败


async def test_budget_left_is_shared_counter(monkeypatch):
    monkeypatch.setattr(mail_queue, "HOURLY_LIMIT", 2)
    await _enqueue(n=2)
    async with SessionLocal() as db:
        assert await mail_queue.budget_left(db) is True
        await mail_queue.drain(db)
        assert await mail_queue.budget_left(db) is False    # 忘记密码也看同一个额度


async def test_concurrent_drains_do_not_double_send(monkeypatch):
    """两个 drain 同时跑（并发请求的后台任务，或 cron 兜底撞上在线请求）时，
    一封信只能被发出去一次 —— 否则用户会收到重复邮件。"""
    import asyncio

    calls: list[str] = []

    async def slow(db, *, to, subject, body_text, body_html="", transport=None):
        await asyncio.sleep(0.05)
        calls.append(to)

    monkeypatch.setattr(mail_sender, "send", slow)
    await _enqueue(to="once@x.test", n=3)
    async with SessionLocal() as a, SessionLocal() as b:
        ra, rb = await asyncio.gather(mail_queue.drain(a), mail_queue.drain(b))
    assert len(calls) == 3, f"实际发出 {len(calls)} 次，重复投递了"
    assert ra["sent"] + rb["sent"] == 3


async def test_enqueue_skips_blank_recipient():
    async with SessionLocal() as db:
        assert await mail_queue.enqueue(db, to="  ", subject="x", body_text="y", kind="test") is None
        await db.commit()
    assert await _rows() == []
