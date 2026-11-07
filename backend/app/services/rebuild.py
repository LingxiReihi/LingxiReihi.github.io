"""前端本机重建：asyncio 子进程 + 全局构建锁 + 10s 合并窗口。
脚本未配置 => job.skipped，URL 入 pending_push（docs/backend-architecture.md §10.3 v1.2 时序）。
事件循环单线程：对 _pending_urls/_debouncer 的读改在两个 await 之间完成即原子，无需额外锁。"""
import asyncio
import shlex
from datetime import datetime, timezone

from ..core.config import settings
from ..core.db import SessionLocal
from ..models import RebuildJob
from . import seo_push, sitemap

_build_lock = asyncio.Lock()      # 同时只跑一个构建
_pending_urls: set[str] = set()
_debouncer: asyncio.Task | None = None

async def _run_job(urls: list[str]) -> None:
    async with _build_lock:
        async with SessionLocal() as db:
            job = RebuildJob(triggered_by="publish")
            db.add(job)
            await db.commit()
            try:
                if not settings.rebuild_script:
                    if settings.rebuild_request_file:
                        # Docker 模式：容器内无法执行构建，写请求文件交给宿主机 watcher（cron）拉起 builder
                        from pathlib import Path
                        from datetime import datetime as _dt
                        p = Path(settings.rebuild_request_file)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(_dt.now(timezone.utc).isoformat() + "\n" + "\n".join(urls), encoding="utf-8")
                        job.status = "requested"
                        job.log = "已写入重建请求，等待宿主机 watcher 构建（≤5 分钟）"
                    else:
                        job.status = "skipped"
                        job.log = "REBUILD_SCRIPT 与 REBUILD_REQUEST_FILE 均未配置，跳过重建"
                    await seo_push.push_urls(db, urls, triggered_by="publish")
                else:
                    proc = await asyncio.create_subprocess_shell(
                        shlex.quote(settings.rebuild_script),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=1800)
                    tail = (out or b"").decode(errors="replace")[-3000:]
                    if proc.returncode == 0:
                        job.status = "success"
                        job.log = tail
                        sitemap.invalidate()
                        await seo_push.push_urls(db, urls, triggered_by="publish")
                    else:
                        job.status = "failed"
                        job.log = f"exit={proc.returncode}\n{tail}"
            except Exception as e:  # noqa: BLE001
                job.status = "failed"
                job.log = repr(e)[:3000]
            finally:
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()


async def reconcile_requested() -> int:
    """把还停在 requested 的 job 对账成 success —— 依据是宿主机 watcher **只在构建成功时**删请求文件。

    Docker 模式下后端不动构建，这是它能拿到的最强信号：请求文件没了 ⇔ watcher 建完了。
    watcher 失败时会保留文件等下次重试，所以这条对账不会把失败误报成成功。
    返回被改动的行数（SEO 面板拉任务列表时调一次，让「重建完成」在界面上看得见）。
    """
    from pathlib import Path
    from sqlalchemy import select
    if not settings.rebuild_request_file or Path(settings.rebuild_request_file).exists():
        return 0
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(RebuildJob).where(RebuildJob.status == "requested"))).scalars().all()
        now = datetime.now(timezone.utc)
        for job in rows:
            job.status = "success"
            job.log = (job.log + "\n" if job.log else "") + "宿主机 watcher 已消费重建请求，构建完成"
            job.finished_at = now
        await db.commit()
        return len(rows)


async def _flush_window() -> None:
    global _debouncer
    await asyncio.sleep(max(settings.rebuild_merge_seconds, 0))
    urls = list(_pending_urls)
    _pending_urls.clear()
    _debouncer = None
    if urls:
        await _run_job(urls)


def trigger_rebuild(urls: list[str]) -> dict:
    """发布钩子（同步入口，非阻塞）。10s 窗口内的多次发布合并为一次构建。"""
    global _debouncer
    merged = bool(_pending_urls)
    _pending_urls.update(urls)
    if _debouncer is None:
        _debouncer = asyncio.create_task(_flush_window())
    return {"queued": True, "merged_with_previous": merged}
