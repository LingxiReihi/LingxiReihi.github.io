"""管理员「忘记密码」编排：随机口令 → 邮件送达 → 才改库。

响应口径（唯一对外话术见 UNIFORM_MESSAGE）：账号不存在、已停用、没填邮箱、
被冷却挡下、发信失败，全部返回同一句话。差别本身就是可枚举的信息，
所以这里只把真实原因写进服务端日志。
"""
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.errors import AppException, ErrorCode
from ..core.logs import log_event
from . import admin_accounts
from . import auth as auth_svc
from . import mail_queue, mail_sender
from .settings import get_group

COOLDOWN_SECONDS = 60          # 同一账号两封之间的最短间隔
PER_ACCOUNT_HOURLY = 3         # 同一账号每小时最多三封
GLOBAL_HOURLY = 20             # 全站每小时上限：QQ 邮箱被风控就等于全站的验证码都发不出
_WINDOW_SECONDS = 3600

UNIFORM_MESSAGE = ("如果该账号可以自助重置，新口令已发到它绑定的邮箱；"
                   "请稍等几分钟并检查垃圾邮件，仍然没收到就请联系顶级管理员")

_last_sent: dict[str, float] = {}
_sent_log: list[tuple[str, float]] = []


def _prune(now: float) -> None:
    """滚动清理：两条状态都只保留窗口内的条目，避免任何一路提前返回把窗口留成死数据。"""
    _sent_log[:] = [(n, t) for n, t in _sent_log if now - t < _WINDOW_SECONDS]
    for stale in [k for k, v in _last_sent.items() if now - v >= _WINDOW_SECONDS]:
        del _last_sent[stale]


def _throttled(name: str, now: float) -> bool:
    if now - _last_sent.get(name, -1e18) < COOLDOWN_SECONDS:
        return True
    if len(_sent_log) >= GLOBAL_HOURLY:
        return True
    return sum(1 for n, _ in _sent_log if n == name) >= PER_ACCOUNT_HOURLY


def _record(name: str, now: float) -> None:
    _last_sent[name] = now
    _sent_log.append((name, now))


def _mail_body(title: str, username: str, password: str) -> str:
    return (
        f"{title} 管理员口令重置\n\n"
        f"账号：{username}\n新口令：{password}\n\n"
        f"请用它在 {settings.site_url.rstrip('/')}/admin/login 登录，"
        "登录后尽快到「站点设置 → 账号安全」换成自己的口令。\n"
        "本次重置已让该账号的所有旧登录设备下线。\n"
        "如果这不是你发起的操作，请忽略本邮件并尽快告知其他管理员。"
    )


async def request(db: AsyncSession, username: str) -> str:
    """受理一次自助重置。永远返回同一句话（除通道未配置 —— 那是站点故障，与账号无关）。"""
    name = (username or "").strip()
    now = time.monotonic()
    _prune(now)
    cfg = await mail_sender.mail_config(db)
    if not mail_sender.channel_ready(cfg):
        raise AppException(ErrorCode.SERVICE_UNAVAILABLE,
                           "邮件通道未配置，暂时无法自助重置，请联系顶级管理员")
    # 口令信**不进队列**（明文不能在库里等下一小时），但和评论通知抢同一个发信邮箱，
    # 所以共用一份额度；额度满了就明确报错，而不是悄悄排队让人干等
    if not await mail_queue.budget_left(db):
        raise AppException(ErrorCode.SERVICE_UNAVAILABLE,
                           "发信额度已用尽，请稍后再试，或联系顶级管理员代重置")
    if _throttled(name, now):
        log_event("auth", f"忘记密码被冷却挡下 username={name}", level="warning")
        return UNIFORM_MESSAGE

    user = await auth_svc.get_user_by_name(db, name)
    if not user:
        log_event("auth", f"忘记密码：账号不存在 username={name}", level="warning")
        return UNIFORM_MESSAGE
    if not user.is_active:
        log_event("auth", f"忘记密码：账号已停用 username={name}", level="warning")
        return UNIFORM_MESSAGE
    if not user.email:
        log_event("auth", f"忘记密码：账号未填邮箱 username={name}", level="warning")
        return UNIFORM_MESSAGE

    title = (await get_group(db, "site")).get("title") or "personal-web"
    password = admin_accounts.gen_password()
    admin_accounts.apply_reset(user, password)
    subject = f"【{title}】管理员 {name} 的口令已重置"
    try:
        await mail_sender.send(db, to=user.email, subject=subject,
                               body_text=_mail_body(title, name, password))
    except mail_sender.MailError as e:
        await db.rollback()      # 发不出去就不改口令：整笔回滚，旧口令继续可用
        log_event("auth", f"忘记密码：发信失败 username={name} reason={e}", level="warning")
        return UNIFORM_MESSAGE
    await mail_queue.record_direct_send(db, to=user.email, subject=subject, kind="forgot_password")
    await db.commit()
    _record(name, now)
    log_event("auth", f"忘记密码：新口令已发往绑定邮箱 username={name}", actor=name)
    return UNIFORM_MESSAGE
