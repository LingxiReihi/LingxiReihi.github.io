"""来源分布分类口径（站内自跳算 direct）+ 前端上报落地来源 + 重建任务的对账（watcher 消费即完成）。"""
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import RebuildJob, ViewEvent
from app.services.rebuild import reconcile_requested
from app.services.stats import classify_referrer, sources


def _today() -> int:
    return int(datetime.now(timezone.utc).strftime("%Y%m%d"))


async def _stored_referrers():
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(ViewEvent.id, ViewEvent.referrer).order_by(ViewEvent.id))).all()
    return [r for _, r in rows]


async def test_google_landing_is_counted_as_search(client):
    await client.get("/api/v1/home?track_local=1",
                     headers={"X-Page-Referrer": "https://www.google.com/"})
    await client.get("/api/v1/home?track_local=1",
                     headers={"X-Page-Referrer": "https://www.bing.com/"})
    await client.get("/api/v1/home?track_local=1",
                     headers={"Referer": "https://example.com/post-one"})
    assert await _stored_referrers() == [
        "https://www.google.com/", "https://www.bing.com/", "https://example.com/post-one"]
    async with SessionLocal() as db:
        d = _today()
        data = await sources(db, d, d)
    assert (data["search"], data["direct"], data["other"]) == (2, 1, 0)


async def test_malformed_client_referrer_falls_back_to_referer(client):
    await client.get("/api/v1/home?track_local=1",
                     headers={"X-Page-Referrer": "javascript:alert(1)",
                              "Referer": "https://www.baidu.com/s?wd=x"})
    assert await _stored_referrers() == ["https://www.baidu.com/s?wd=x"]


async def test_client_without_report_keeps_old_behaviour(client):
    await client.get("/api/v1/home?track_local=1", headers={"Referer": "https://ref.example/"})
    assert await _stored_referrers() == ["https://ref.example/"]


def test_own_site_referrer_counts_as_direct_not_other():
    """站内列表→详情、详情→关于页的跳转不是「外部来源」，此前全被算进其他。"""
    assert classify_referrer("https://example.com/blog/post-one") == "direct"
    assert classify_referrer("https://www.example.com/") == "direct"      # 裸域与 www 都算自站
    assert classify_referrer("http://example.com/chats") == "direct"


def test_lookalike_host_is_not_treated_as_own_site():
    assert classify_referrer("https://example.com.evil.com/x") == "other"


def test_external_sources_still_classified():
    assert classify_referrer("") == "direct"
    assert classify_referrer("https://www.baidu.com/link?url=abc") == "search"
    assert classify_referrer("https://yandex.com/search/?text=x") == "search"
    assert classify_referrer("https://duckduckgo.com/") == "search"
    assert classify_referrer("https://www.zhihu.com/account") == "social"
    assert classify_referrer("https://news.ycombinator.com/item?id=1") == "other"


async def _new_job(status="requested"):
    async with SessionLocal() as db:
        job = RebuildJob(status=status, triggered_by="publish", log="已写入重建请求")
        db.add(job)
        await db.commit()
        return job.id


async def _status(job_id):
    async with SessionLocal() as db:
        job = await db.get(RebuildJob, job_id)
        return job.status, job.log, job.finished_at


async def test_requested_job_waits_while_request_file_still_exists(tmp_path):
    req = tmp_path / ".rebuild-request"
    req.write_text("2026-10-07T00:00:00+00:00\nhttps://example.com/blog/x", encoding="utf-8")
    old, settings.rebuild_request_file = settings.rebuild_request_file, str(req)
    try:
        jid = await _new_job()
        assert await reconcile_requested() == 0
        assert (await _status(jid))[0] == "requested"
    finally:
        settings.rebuild_request_file = old


async def test_requested_job_flips_to_success_once_watcher_consumed_it(tmp_path):
    """watcher 只在构建成功时删请求文件，所以「文件没了」就是完成的确证，不会误报。"""
    req = tmp_path / ".rebuild-request"
    req.write_text("x", encoding="utf-8")
    old, settings.rebuild_request_file = settings.rebuild_request_file, str(req)
    try:
        jid = await _new_job()
        await reconcile_requested()                       # 文件还在：不动
        req.unlink()
        assert await reconcile_requested() == 1
        status, log, finished = await _status(jid)
        assert status == "success" and finished is not None
        assert "watcher" in log and "完成" in log
        assert await reconcile_requested() == 0           # 幂等：没有待对账的行了
    finally:
        settings.rebuild_request_file = old


async def test_reconcile_skips_unconfigured_request_file():
    old, settings.rebuild_request_file = settings.rebuild_request_file, ""
    try:
        jid = await _new_job("requested")
        assert await reconcile_requested() == 0
        assert (await _status(jid))[0] == "requested"     # 宿主脚本模式下不该有 requested 行
    finally:
        settings.rebuild_request_file = old
