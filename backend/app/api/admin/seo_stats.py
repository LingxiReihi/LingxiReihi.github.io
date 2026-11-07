"""监控看板 + SEO 面板端点（Flow H / §5.6）。"""
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx, get_page, parse_day_params
from ...core.errors import AppException, ErrorCode, ok
from ...models import PushLog, RebuildJob
from ...services import rebuild, seo_push, stats as stats_svc

stats_router = APIRouter(prefix="/stats", tags=["admin-stats"])
seo_router = APIRouter(prefix="/seo", tags=["admin-seo"])


async def _stats_view(ctx: AdminContext = Depends(get_admin_ctx)) -> AdminContext:
    ctx.need("stats:view", subject="数据看板")
    return ctx


async def _super_only(ctx: AdminContext = Depends(get_admin_ctx)) -> AdminContext:
    """百度推送与前端重建是站点级动作（影响全站收录与线上产物），不下放给普通管理员。"""
    if not ctx.is_super:
        raise AppException(ErrorCode.FORBIDDEN, "该操作只允许顶级管理员执行")
    return ctx


@stats_router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), _: AdminContext = Depends(_stats_view)):
    return ok(await stats_svc.overview(db))


@stats_router.get("/trend")
async def trend(start: str | None = None, end: str | None = None,
                db: AsyncSession = Depends(get_db), _: AdminContext = Depends(_stats_view)):
    s, e = parse_day_params(start, end, default_days=7)
    return ok({"days": await stats_svc.trend(db, s, e)})


@stats_router.get("/top-content")
async def top_content(range: str = Query("7d"), limit: int = Query(10, le=50),
                      type: str | None = None, db: AsyncSession = Depends(get_db),
                      _: AdminContext = Depends(_stats_view)):
    s, e = _range_to_days(range)
    return ok({"items": await stats_svc.top_content(db, s, e, limit, type)})


@stats_router.get("/content/{content_id}")
async def content_drill(content_id: int, start: str | None = None, end: str | None = None,
                        db: AsyncSession = Depends(get_db), _: AdminContext = Depends(_stats_view)):
    s, e = parse_day_params(start, end, default_days=30)
    return ok(await stats_svc.content_detail(db, content_id, s, e))


@stats_router.get("/sources")
async def sources(range: str = "7d", db: AsyncSession = Depends(get_db),
                  _: AdminContext = Depends(_stats_view)):
    s, e = _range_to_days(range)
    return ok(await stats_svc.sources(db, s, e))


@stats_router.get("/export")
async def export(start: str | None = None, end: str | None = None,
                 db: AsyncSession = Depends(get_db), _: AdminContext = Depends(_stats_view)):
    s, e = parse_day_params(start, end, default_days=30)
    rows = await stats_svc.export_rows(db, s, e)
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename=stats-{s}-{e}.csv"})


def _range_to_days(r: str) -> tuple[int, int]:
    import datetime as dt
    end = int(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d"))
    n = {"7d": 6, "30d": 29, "90d": 89}.get(r, 6)
    start = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=n)).strftime("%Y%m%d"))
    return start, end


# ── SEO 面板 ──

@seo_router.get("/config")
async def seo_config(db: AsyncSession = Depends(get_db), _: AdminContext = Depends(_stats_view)):
    return ok({"push_enabled": settings.seo_push_enabled,
               "api_configured": bool(settings.baidu_push_api),
               "rebuild_configured": bool(settings.rebuild_script),
               "rebuild_watcher": bool(settings.rebuild_request_file),
               "site_url": settings.site_url})


@seo_router.post("/push")
async def manual_push(body: dict, db: AsyncSession = Depends(get_db),
                      ctx: AdminContext = Depends(_super_only)):
    from ...models import Content, PendingPush
    from ...core.logs import log_event
    urls: list[str] = list(body.get("urls", []))
    for cid in body.get("content_ids", []):
        c = await db.get(Content, int(cid))
        if c:
            from .contents import public_path
            urls.append(public_path(c, settings.site_url.rstrip("/")))
    if body.get("pending"):
        rows = await seo_push.pending_urls(db)
        urls += [r.url for r in rows]
        await seo_push.clear_pending(db, rows)
    if not urls:
        return ok({"success": 0, "fail": 0, "skipped": 0, "already": 0, "notice": ["无可推送 URL"]})
    # 默认跳过已推送过的地址；确实要重推时前端显式传 force
    result = await seo_push.push_urls(db, list(dict.fromkeys(urls)), triggered_by="manual",
                                      force=bool(body.get("force")))
    log_event("push", f"百度推送 {len(urls)} 条：success={result.get('success')} fail={result.get('fail')} "
                      f"已推跳过={result.get('already')} 入待推={result.get('skipped')}",
              actor=ctx.user.username)
    return ok(result)


@seo_router.get("/push-logs")
async def push_logs(pg=Depends(get_page), db: AsyncSession = Depends(get_db),
                    _: AdminContext = Depends(_stats_view)):
    import json
    rows = (await db.execute(select(PushLog).order_by(PushLog.id.desc())
                             .offset(pg.offset).limit(pg.page_size))).scalars().all()
    return ok({"total": len(rows), "page": pg.page, "page_size": pg.page_size,
               "items": [{"id": r.id, "urls": json.loads(r.urls_json or "[]"),
                          "result": json.loads(r.result_json or "{}"),
                          "triggered_by": r.triggered_by, "created_at": r.created_at} for r in rows]})


@seo_router.post("/rebuild")
async def trigger(body: dict | None = None, db: AsyncSession = Depends(get_db),
                  ctx: AdminContext = Depends(_super_only)):
    from ...models import PendingPush
    urls = list(body.get("urls", [])) if body else []
    if not urls:
        urls = list(dict.fromkeys(r.url for r in (await db.execute(select(PendingPush))).scalars().all()))
    info = rebuild.trigger_rebuild(urls or ["__sitemap__"])
    from ...core.logs import log_event
    log_event("rebuild", f"手动触发重建（{len(urls)} 个 URL）→ {info}", actor=ctx.user.username)
    return ok(info)


@seo_router.get("/jobs")
async def jobs(pg=Depends(get_page), db: AsyncSession = Depends(get_db),
               _: AdminContext = Depends(_stats_view)):
    # 先看一眼宿主机 watcher 有没有把请求文件消费掉，有就把 requested 改成 success 再列出来
    await rebuild.reconcile_requested()
    rows = (await db.execute(select(RebuildJob).order_by(RebuildJob.id.desc())
                             .offset(pg.offset).limit(pg.page_size))).scalars().all()
    return ok({"items": [{"id": j.id, "status": j.status, "log": j.log[-500:],
                          "triggered_by": j.triggered_by, "created_at": j.created_at,
                          "finished_at": j.finished_at} for j in rows]})
