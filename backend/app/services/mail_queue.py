"""出站发信队列：谁都不直发，先入队，再由 drain 按额度与退避节奏发出去。

设计要点（都是"为什么"，不是"是什么"）：
- 额度与退避**从表本身推导**，不另存进程内状态：后端随时会重启/重建，内存计数会清零，
  而「超额攒到下一小时发」是个跨重启的承诺。顺带好处是随时能查积压与最近错误。
- 状态只有 pending / sent / dropped：等待重试的行仍是 pending（配 attempts>0），
  避免出现「failed 但其实还会再发」这种两处真相。
- 通道未配置（站点压根没填 Key）算**延后**，不算失败：不烧 attempts、不触发退避。
- 带明文口令的重置邮件**不走这里**（见 services/password_reset.py），它只借用同一份额度。
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import SessionLocal, utcnow
from ..core.logs import log_event
from ..models import MailQueue
from . import mail_sender

HOURLY_LIMIT = 30            # 全站总预算：忘记密码 + 作者通知 + 评论者通知共用
MAX_ATTEMPTS = 5             # 用尽即 dropped，防永久堆积
RETRY_DELAY = timedelta(hours=1)
PAUSE_MINUTES = 30           # 退避时长：连续失败后整条队列暂停
BACKOFF_WINDOW = timedelta(minutes=15)
BACKOFF_FAILS = 3            # 窗口内 ≥3 次失败且最新一次仍是失败 → 退避
DRAIN_BATCH = 100


async def enqueue(db: AsyncSession, *, to: str, subject: str, body_text: str,
                  body_html: str = "", kind: str, comment_id: int | None = None) -> MailQueue | None:
    """入队但不 commit —— 让调用方决定与业务写入是否同一笔事务。收件人为空则跳过。"""
    addr = (to or "").strip()
    if not addr:
        return None
    row = MailQueue(to_addr=addr, subject=subject[:200], body_text=body_text,
                    body_html=body_html, kind=kind, comment_id=comment_id)
    db.add(row)
    return row


async def _due(db: AsyncSession, now: datetime) -> list[MailQueue]:
    rows = await db.execute(
        select(MailQueue).where(MailQueue.status == "pending", MailQueue.next_try_at <= now)
        .order_by(MailQueue.id).limit(DRAIN_BATCH))
    return list(rows.scalars().all())


async def _failures(db: AsyncSession, now: datetime) -> list[MailQueue]:
    """窗口内的失败结局：等待重试的 pending（attempts>0）与已丢弃的都算。"""
    rows = await db.execute(
        select(MailQueue).where(
            MailQueue.attempts > 0,
            MailQueue.status.in_(("pending", "dropped")),
            MailQueue.updated_at >= now - BACKOFF_WINDOW).order_by(MailQueue.updated_at.desc()))
    return list(rows.scalars().all())


async def _last_success(db: AsyncSession, now: datetime) -> datetime | None:
    return (await db.execute(
        select(func.max(MailQueue.updated_at)).where(
            MailQueue.status == "sent",
            MailQueue.updated_at >= now - BACKOFF_WINDOW))).scalar_one_or_none()


async def paused_until(db: AsyncSession, now: datetime | None = None) -> datetime | None:
    """连续拒收退避：窗口内 ≥3 次失败 → 暂停到最后一次失败 + 30 分钟。

    中途若有一封成功发出去，说明对端活着，只是这封信本身有问题，不再连坐整条队列。
    """
    now = now or utcnow()
    fails = await _failures(db, now)
    if len(fails) < BACKOFF_FAILS:
        return None
    last_fail = max(r.updated_at for r in fails)
    ok_at = await _last_success(db, now)
    if ok_at and ok_at > last_fail:
        return None
    return last_fail + timedelta(minutes=PAUSE_MINUTES)


async def budget_left(db: AsyncSession, now: datetime | None = None) -> bool:
    """最近 1 小时用掉多少封 —— 忘记密码在直发前也查这同一个额度。"""
    now = now or utcnow()
    sent = (await db.execute(
        select(func.count()).select_from(MailQueue).where(
            MailQueue.status == "sent", MailQueue.updated_at >= now - timedelta(hours=1))
    )).scalar_one()
    return int(sent) < HOURLY_LIMIT


async def drain(db: AsyncSession, *, now: datetime | None = None) -> dict:
    """按额度与退避把到点的信发出去。返回各结局计数，deferred = 本轮没发但也没丢。"""
    now = now or utcnow()
    stats = {"sent": 0, "failed": 0, "dropped": 0, "deferred": 0}
    due = await _due(db, now)
    if not due:
        return stats
    cfg = await mail_sender.mail_config(db)
    if not mail_sender.channel_ready(cfg):
        stats["deferred"] = len(due)
        return stats                       # 站点没开通知：静默延后，不记失败
    until = await paused_until(db, now)
    if until and now < until:
        stats["deferred"] = len(due)
        log_event("mail", f"发信退避中（暂停至 {until:%H:%M}），本批 {len(due)} 封延后", level="warning")
        return stats
    for row in due:
        if not await budget_left(db, now):
            stats["deferred"] += 1
            continue
        # 先占位再发：把 next_try_at 推到一小时后并立即提交，rowcount!=1 说明这行已被
        # 另一个 drain 抢走（并发请求的后台任务会撞，cron 兜底也会和在跑的业务请求撞），
        # 不占位就会出现"一封信发两次"。崩溃在占位之后也只是晚一小时重试，不会丢。
        claim = await db.execute(
            update(MailQueue)
            .where(MailQueue.id == row.id, MailQueue.status == "pending",
                   MailQueue.next_try_at <= now)
            .values(next_try_at=now + RETRY_DELAY))
        if claim.rowcount != 1:
            continue
        await db.commit()
        try:
            await mail_sender.send(db, to=row.to_addr, subject=row.subject,
                                   body_text=row.body_text, body_html=row.body_html or "")
        except mail_sender.MailError as e:
            row.attempts += 1
            row.last_error = str(e)[:200]
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "dropped"
                stats["dropped"] += 1
                log_event("mail", f"发信 {row.attempts} 次仍失败，丢弃 id={row.id} kind={row.kind}",
                          level="warning")
            else:
                stats["failed"] += 1
                log_event("mail", f"发信失败，一小时后重试 id={row.id} kind={row.kind} reason={e}",
                          level="warning")
        else:
            row.status = "sent"
            row.last_error = ""
            stats["sent"] += 1
            log_event("mail", f"队列发信成功 id={row.id} kind={row.kind}")
        row.updated_at = utcnow()          # 额度与退避窗口都按真实结局时间算
    await db.commit()
    return stats


async def record_direct_send(db: AsyncSession, *, to: str, subject: str, kind: str) -> None:
    """直发的信也占同一份额度：记一条**无正文**的台账行。

    口令类正文绝不能落库（等下一小时就等于把明文口令存在库里），
    所以 body_text 留空 —— 这一行只为数额度与看"最近发过什么"存在。
    """
    db.add(MailQueue(to_addr=(to or "").strip(), subject=subject[:200], body_text="",
                     kind=kind, status="sent", attempts=0, last_error=""))


async def drain_now() -> dict:
    """给后台任务与 CLI 用：自开 session，不借请求作用域的会话。"""
    async with SessionLocal() as db:
        return await drain(db)


async def summary(db: AsyncSession) -> dict:
    """给 CLI / 排障用：各状态计数 + 最近一条错误。"""
    counts = dict((await db.execute(
        select(MailQueue.status, func.count()).group_by(MailQueue.status))).all())
    last = (await db.execute(
        select(MailQueue).where(MailQueue.last_error != "").order_by(MailQueue.updated_at.desc())
        .limit(1))).scalars().first()
    return {"counts": {k: int(v) for k, v in counts.items()},
            "hourly_limit": HOURLY_LIMIT,
            "paused_until": (await paused_until(db)).isoformat(timespec="minutes")
            if await paused_until(db) else None,
            "budget_left": await budget_left(db),
            "last_error": (last.last_error if last else "")}
