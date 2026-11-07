"""公告发布 → 给所有在职管理员入队一封通知信。

不变式（与设计一致）：
- 只有「首次发布」触发（新建即 published，或草稿转发布）；编辑已发布公告不重发。
- 收件人 = is_active 且填了邮箱的每个管理员，各一行；停用或无邮箱者跳过。
- 邮件是增益不是关卡：入队失败绝不回滚公告。
断言看的是 mail_queue 行本身（conftest 清空了 MAIL_* env，通道未配置 → drain 只延后不发，
行会留在 pending，正好可断言）。
"""
import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import MailQueue, User


async def _set_email(username: str, email: str | None):
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.username == username))).scalar_one()
        u.email = email
        await db.commit()


async def _set_active(username: str, active: bool):
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.username == username))).scalar_one()
        u.is_active = active
        await db.commit()


async def _queue(kind: str = "announcement"):
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(MailQueue).where(MailQueue.kind == kind).order_by(MailQueue.id)
        )).scalars().all()
        return list(rows)


async def _create(auth, **over):
    body = {"title": "v3 发布通知", "body_md": "## 变更\n- 加了邮件通知", "status": "published",
            "published_at": "2026-10-14T12:00:00+00:00"}
    body.update(over)
    return await auth.post("/api/v1/admin/announcements", json=body)


@pytest.mark.asyncio
async def test_publish_queues_one_mail_per_active_admin(auth, make_staff):
    await _set_email("admin", "root@example.test")
    await make_staff("n_a")                      # make_staff 默认带 email
    await make_staff("n_b")
    r = await _create(auth)
    assert r.status_code == 200
    rows = await _queue()
    assert {x.to_addr for x in rows} == {"root@example.test", "n_a@example.test", "n_b@example.test"}
    assert all(x.status == "pending" and x.kind == "announcement" for x in rows)
    assert "v3 发布通知" in rows[0].subject
    assert "/admin/announcements" in rows[0].body_text
    assert "加了邮件通知" in rows[0].body_text


@pytest.mark.asyncio
async def test_draft_publishes_no_mail(auth):
    await _set_email("admin", "root@example.test")
    assert (await _create(auth, status="draft", published_at=None)).status_code == 200
    assert await _queue() == []


@pytest.mark.asyncio
async def test_draft_to_published_queues_then_edit_does_not_resend(auth):
    await _set_email("admin", "root@example.test")
    a = (await _create(auth, status="draft", published_at=None)).json()["data"]
    assert await _queue() == []
    r = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"status": "published"})
    assert r.status_code == 200
    assert len(await _queue()) == 1              # 草稿转正式 = 它的首次发布
    await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"title": "改个标题"})
    assert len(await _queue()) == 1              # 编辑已发布不重发
    await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"body_md": "补一行"})
    assert len(await _queue()) == 1


@pytest.mark.asyncio
async def test_inactive_and_emailless_admins_are_skipped(auth, make_staff):
    await make_staff("no_mail")
    await _set_email("no_mail", None)            # make_staff 会给默认邮箱，要真空就得显式清空
    await make_staff("gone")
    await _set_active("gone", False)
    assert (await _create(auth)).status_code == 200
    assert await _queue() == []                  # admin 自己也没填邮箱 → 一个可用收件人都没有


@pytest.mark.asyncio
async def test_subject_is_flat_even_if_title_has_newline(auth):
    await _set_email("admin", "root@example.test")
    assert (await _create(auth, title="一行\n二行")).status_code == 200
    rows = await _queue()
    assert len(rows) == 1
    assert "\n" not in rows[0].subject and "  " not in rows[0].subject


@pytest.mark.asyncio
async def test_announcement_survives_when_notify_cannot_run(auth, monkeypatch):
    """入队炸了也不能把公告保存一起带走（邮件是旁路，不是关卡）。"""
    from app.services import announcement_notify

    async def boom(*a, **kw):
        raise RuntimeError("queue down")
    monkeypatch.setattr(announcement_notify, "enqueue_for_published", boom)
    r = await _create(auth)
    assert r.status_code == 200 and r.json()["data"]["title"] == "v3 发布通知"
    async with SessionLocal() as db:
        assert int((await db.execute(select(func.count()).select_from(MailQueue))).scalar_one()) == 0

@pytest.mark.asyncio
async def test_mail_body_is_rendered_html_and_not_clipped(auth):
    """正文按 Markdown 渲染成 HTML，且不再有 300 字截断。"""
    await _set_email("admin", "root@example.test")
    long_md = "## 长公告\n\n" + ("这是一段很长的正文。" * 200)     # ≈2000 字，远超旧的 300 字上限
    assert (await _create(auth, body_md=long_md)).status_code == 200
    rows = await _queue()
    assert len(rows) == 1
    html = rows[0].body_html
    assert "<h2>长公告</h2>" in html                  # Markdown 标题已渲染
    assert "<p>" in html
    assert long_md.split("\n\n", 1)[1] in rows[0].body_text      # 纯文本兜底保留全文
    assert "…" not in rows[0].body_text                # 没有被截断
