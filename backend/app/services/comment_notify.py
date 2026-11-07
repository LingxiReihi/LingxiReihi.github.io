"""评论相关的两封通知信：作者（有人评论了她的内容）与评论者（评论首次通过审核）。

两封都**进队列而不是直发**：出信节奏、额度与退避由 `mail_queue` 统一管，
这里只负责"该不该发、发给谁、写什么"。

去重口径：给评论者的信靠 `comments.notified_at`（持久列），不靠"队列里有没有行" ——
所以「通过→拒绝→再通过」也只发一封，重启或队列被清空都不会重发。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import mail_html
from ..core.config import settings
from ..core.db import SessionLocal, utcnow
from ..core.logs import log_event
from ..models import Comment, Content, User
from . import mail_queue
from .profiles import super_user
from .settings import get_group
from .sitemap import TYPE_PATH

TYPE_LABEL = {"article": "文章", "model": "模型", "chat": "杂谈"}


def _base_url() -> str:
    return settings.site_url.rstrip("/")


def _content_url(c: Content) -> str:
    if c.type == "chat":
        return f"{_base_url()}/chats/{c.id}"
    return f"{_base_url()}/{TYPE_PATH[c.type]}/{c.slug}" if c.slug else _base_url()


def _flat(text: str) -> str:
    """主题里不能有换行/连续空白（对端建信头时会拒绝，等于白白烧一次发信）。"""
    return " ".join(text.split())


async def _recipient(db: AsyncSession, c: Content) -> tuple[str, str, str]:
    """(邮箱, 账号名, 落点说明)；一个可用收件人都没有时返回空三元组。"""
    owner = await db.get(User, c.created_by_id) if c.created_by_id else None
    for cand, why in ((owner, "内容作者"), (await super_user(db), "回落顶级管理员")):
        if cand is not None and cand.is_active and cand.email:
            return cand.email, cand.username, why
    return "", "", ""


def _author_mail(c: Content, comment: Comment) -> tuple[str, str]:
    """(纯文本兜底, HTML)。评论正文按 Markdown 渲染，全文不截断。"""
    text = (
        f"《{c.title}》收到一条新评论，正在等待审核。\n\n"
        f"评论者：{comment.nickname} <{comment.email}>\n"
        f"提交时间：{comment.created_at:%Y-%m-%d %H:%M} UTC\n"
        f"所在内容：{TYPE_LABEL.get(c.type, c.type)} · {_content_url(c)}\n\n"
        f"—— 评论正文 ——\n{comment.body}\n\n"
        f"去后台审核：{_base_url()}/admin/comments"
    )
    link = f"{_base_url()}/admin/comments"
    html = mail_html.document(
        kicker="待审核评论",
        title=f"《{c.title}》收到一条新评论",
        meta=f"{comment.nickname} <{comment.email}> · {comment.created_at:%Y-%m-%d %H:%M} UTC",
        body_md=comment.body,
        foot_html=(
            f'所在内容：<a href="{_content_url(c)}" style="color:{mail_html.ACCENT}">{TYPE_LABEL.get(c.type, c.type)}</a>'
            f'　·　<a href="{link}" style="color:{mail_html.ACCENT}">去后台审核</a>'
        ),
    )
    return text, html


def _visitor_mail(site: str, c: Content, comment: Comment) -> tuple[str, str]:
    text = (
        f"你在「{site}」的评论已通过审核，现在公开可见了。\n\n"
        f"内容：《{c.title}》\n"
        f"链接：{_content_url(c)}\n"
        f"你的评论：{comment.nickname}\n{comment.body}\n\n"
        f"如果这不是你本人的操作，请到前台删除该评论或告知站点管理员。"
    )
    html = mail_html.document(
        kicker="评论已通过",
        title=f"你在「{site}」的评论已通过审核",
        meta=f"《{c.title}》 · {comment.nickname}",
        body_md=comment.body,
        foot_html=(
            f'<a href="{_content_url(c)}" style="color:{mail_html.ACCENT}">查看内容</a>'
            f'　·　如果不是你本人的操作，请到前台删除该评论或告知站点管理员。'
        ),
    )
    return text, html


async def notify(content_id: int, comment_id: int) -> None:
    """作者通知：新评论提交后由后台任务调用（自开 session，不借请求作用域的会话）。"""
    async with SessionLocal() as db:
        c = await db.get(Content, content_id)
        comment = await db.get(Comment, comment_id)
        if c is None or comment is None:
            return
        to, who, why = await _recipient(db, c)
        if not to:
            log_event("comment", f"评论通知无可用收件人（作者与顶级管理员都没填邮箱）"
                                 f"content_id={content_id}", level="warning")
            return
        site = (await get_group(db, "site")).get("title") or "personal-web"
        body_text, body_html = _author_mail(c, comment)
        await mail_queue.enqueue(
            db, to=to, subject=_flat(f"【{site}】《{c.title}》收到新评论"),
            body_text=body_text, body_html=body_html, kind="comment_author")
        await db.commit()
        await mail_queue.drain(db)                  # 顺带冲刷：额度/退避没放行就只是入队
        log_event("comment", f"评论通知已入队 content_id={content_id} 收件人={who}（{why}）")


async def queue_visitor_notice(db: AsyncSession, comment: Comment, content: Content) -> bool:
    """首次通过时给评论者入队一封。与 `notified_at` 同一笔事务，去重才是持久的。"""
    if comment.notified_at is not None:
        return False
    comment.notified_at = utcnow()
    site = (await get_group(db, "site")).get("title") or "personal-web"
    body_text, body_html = _visitor_mail(site, content, comment)
    await mail_queue.enqueue(
        db, to=comment.email, subject=_flat(f"【{site}】你的评论已通过审核：《{content.title}》"),
        body_text=body_text, body_html=body_html,
        kind="comment_visitor", comment_id=comment.id)
    return True
