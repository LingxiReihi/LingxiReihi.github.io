"""公告首次发布 → 给所有在职管理员各入队一封通知信。

与评论通知同一条链路（都进 `mail_queue`，不直发），所以额度、退避、重试由队列统一管，
这里只决定「该不该发、发给谁、写什么」。三条口径是拍死的：

- 只有**首次发布**触发（新建即 published，或草稿转发布）。编辑已发布公告不重发；
  「改回草稿再发布」会再发一封 —— 靠状态转换判定，不给 mail_queue 加公告外键列。
- 收件人 = `is_active` 且填了邮箱的**每一个**管理员，含操作者本人（与 About 名单同口径）。
  没邮箱的人静默跳过：这是设计里既有的现实（线上目前只有 admin 填了邮箱）。
- 邮件是增益不是关卡：本服务的任何异常都由调用方吞掉记 warning，**绝不把公告保存一起回滚**。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import mail_html
from ..core.config import settings
from ..core.db import SessionLocal
from ..core.logs import log_event
from ..models import Announcement, User
from . import mail_queue
from .settings import get_group

def _base_url() -> str:
    return settings.site_url.rstrip("/")


def _flat(text: str) -> str:
    """主题里不能有换行/连续空白（对端建信头会拒绝，等于白白烧一次发信额度）。"""
    return " ".join(text.split())


def _meta(a: Announcement) -> tuple[str, str]:
    date = (a.published_at or a.created_at)
    author = a.created_by.nickname if a.created_by else "管理员"
    return f"{date:%Y-%m-%d}", author


def _text(a: Announcement, site: str) -> str:
    """纯文本兜底：全文，不截断。"""
    date, author = _meta(a)
    return (
        f"「{site}」发布了一条新的更新公告。\n\n"
        f"标题：{a.title}\n"
        f"日期：{date}\n"
        f"作者：{author}\n\n"
        f"—— 正文 ——\n{a.body_md}\n\n"
        f"登录后查看完整内容：{_base_url()}/admin/announcements"
    )


def _html(a: Announcement, site: str) -> str:
    """HTML 正文：公告的 Markdown 原文按 Markdown 渲染。"""
    date, author = _meta(a)
    link = f"{_base_url()}/admin/announcements"
    return mail_html.document(
        kicker="更新公告",
        title=a.title,
        meta=f"{date} · {author} · {site}",
        body_md=a.body_md,
        foot_html=f'<a href="{link}" style="color:{mail_html.ACCENT}">{link}</a>',
    )


async def enqueue_for_published(db: AsyncSession, a: Announcement) -> int:
    """给每个可用收件人各排一封。返回入队封数；一个可用收件人都没有时记 warning 回 0。"""
    rows = (await db.execute(
        select(User).where(User.is_active, User.email.is_not(None), User.email != "")
    )).scalars().all()
    if not rows:
        log_event("announcement", f"公告通知无可用收件人（在职管理员都没填邮箱）announcement_id={a.id}",
                  level="warning")
        return 0
    site = (await get_group(db, "site")).get("title") or "personal-web"
    subject = _flat(f"【{site}】新公告：《{a.title}》")
    body_text, body_html = _text(a, site), _html(a, site)
    for u in rows:
        await mail_queue.enqueue(db, to=u.email, subject=subject, body_text=body_text,
                                 body_html=body_html, kind="announcement")
    log_event("announcement", f"公告通知已入队 announcement_id={a.id} 收件人 {len(rows)} 位")
    return len(rows)


async def notify_published(announcement_id: int) -> None:
    """后台任务入口：自开 session、只收 id，不借请求作用域的会话（公告此刻早已 commit）。

    整段吞异常 —— 通知炸了也不能把已经保存的公告带回 500，更不能让 ASGI 后台任务抛出裸栈。
    """
    try:
        async with SessionLocal() as db:
            a = await db.get(Announcement, announcement_id)
            if a is None or a.status != "published":
                return
            if not await enqueue_for_published(db, a):
                return
            await db.commit()
            await mail_queue.drain(db)           # 顺带冲刷：额度/退避不放行时就只是留在队列里
    except Exception as e:                       # noqa: BLE001 —— 旁路：只记日志，绝不上抛
        log_event("announcement", f"公告通知失败（公告已保存）announcement_id={announcement_id}: {e}",
                  level="warning")
