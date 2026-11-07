"""新评论 → 通知内容作者的邮件（提交即通知，作者无邮箱/停用则回落 super）。

不变式：通知失败绝不影响评论本身 —— 评论已 commit，通知只是尽力而为的旁路。
自批 2 起作者通知走 mail_queue：入队 + 顺带冲刷，所以断言看的是「drain 后 send 被调用」。
"""
import pytest
from sqlalchemy import select

from app.api import comments as cmod
from app.core.db import SessionLocal
from app.models import Comment, Content, MailQueue, User
from app.services import comment_notify, mail_queue, mail_sender  # noqa: F401  (comment_notify 仍被引用)
from tests.test_public import seed_contents  # noqa: F401


async def _submit(client, content_id, **kw):
    return await client.post("/api/v1/comments", json={
        "content_id": content_id, "nickname": "小明", "email": "xiaoming@example.com",
        "body": "写得好！", **kw})


async def _content_id(client, slug: str) -> int:
    return (await client.get(f"/api/v1/posts/{slug}")).json()["data"]["id"]


async def _set_email(username: str, email: str | None):
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.username == username))).scalar_one()
        u.email = email
        await db.commit()


async def _assign_author(slug: str, username: str, *, active: bool = True) -> int:
    async with SessionLocal() as db:
        c = (await db.execute(select(Content).where(Content.slug == slug))).scalar_one()
        u = (await db.execute(select(User).where(User.username == username))).scalar_one()
        c.created_by_id = u.id
        u.is_active = active
        await db.commit()
        return c.id


@pytest.fixture(autouse=True)
def _clear_state():
    cmod._submit_cooldown.clear()
    yield


@pytest.fixture
def sent(monkeypatch):
    """替掉真出站并声明「通道可用」：conftest 把 MAIL_* env 清空了，不放开就永远走跳过分支。"""
    calls: list[dict] = []

    async def fake(db, *, to, subject, body_text, body_html="", transport=None):
        calls.append({"to": to, "subject": subject, "body_text": body_text})

    monkeypatch.setattr(mail_sender, "send", fake)
    monkeypatch.setattr(mail_sender, "channel_ready", lambda cfg: True)
    return calls


async def test_new_comment_notifies_the_content_author(client, auth, make_staff, sent):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    cid = await _assign_author("post-one", "writer")
    r = await _submit(client, cid)
    assert r.status_code == 200, r.text
    assert [c["to"] for c in sent] == ["writer@x.test"]
    assert "第一篇文章" in sent[0]["subject"]
    body = sent[0]["body_text"]
    assert "小明" in body and "xiaoming@example.com" in body and "写得好！" in body
    assert "/blog/post-one" in body and "/admin/comments" in body


async def test_falls_back_to_super_when_author_has_no_email(client, auth, make_staff, sent):
    await seed_contents()
    await _set_email("admin", "boss@x.test")
    await make_staff("noemail")
    await _assign_author("post-one", "noemail")
    await _set_email("noemail", None)
    cid = await _content_id(client, "post-one")
    assert (await _submit(client, cid)).status_code == 200
    assert [c["to"] for c in sent] == ["boss@x.test"]


async def test_falls_back_when_author_is_inactive(client, auth, make_staff, sent):
    await seed_contents()
    await _set_email("admin", "boss@x.test")
    await make_staff("sleepy", email="sleepy@x.test")
    await _assign_author("post-one", "sleepy", active=False)
    cid = await _content_id(client, "post-one")
    assert (await _submit(client, cid)).status_code == 200
    assert [c["to"] for c in sent] == ["boss@x.test"]


async def test_no_recipient_at_all_still_accepts_the_comment(client, sent):
    await seed_contents()
    cid = await _content_id(client, "post-one")
    assert (await _submit(client, cid)).status_code == 200
    assert sent == []                       # 一封都没发
    async with SessionLocal() as db:
        assert len((await db.execute(select(Comment))).scalars().all()) == 1   # 但评论照常入库


async def test_send_failure_does_not_rollback_the_comment(client, auth, make_staff, monkeypatch):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    cid = await _assign_author("post-one", "writer")

    async def boom(db, **kw):
        raise mail_sender.MailError("对端拒收")

    monkeypatch.setattr(mail_sender, "send", boom)
    monkeypatch.setattr(mail_sender, "channel_ready", lambda cfg: True)
    assert (await _submit(client, cid)).status_code == 200
    async with SessionLocal() as db:
        rows = (await db.execute(select(Comment).where(Comment.content_id == cid))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "pending"


async def test_unconfigured_channel_skips_quietly(client, auth, make_staff, monkeypatch):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    cid = await _assign_author("post-one", "writer")
    calls: list[dict] = []

    async def spy(db, **kw):
        calls.append(kw)

    monkeypatch.setattr(mail_sender, "send", spy)      # 不放开 channel_ready：通道就是未配置态
    assert (await _submit(client, cid)).status_code == 200
    assert calls == []


async def test_honeypot_comment_sends_no_mail(client, auth, make_staff, sent):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    cid = await _assign_author("post-one", "writer")
    assert (await _submit(client, cid, website="http://spam")).status_code == 200
    assert sent == []


async def test_author_notice_is_recorded_in_the_queue(client, auth, make_staff, sent):
    """信发出去了也要留下台账行（额度就是从这张表数出来的）。"""
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    cid = await _assign_author("post-one", "writer")
    assert (await _submit(client, cid)).status_code == 200
    async with SessionLocal() as db:
        rows = (await db.execute(select(MailQueue))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "sent" and rows[0].kind == "comment_author"


async def test_hourly_budget_stops_further_mails(client, auth, make_staff, sent, monkeypatch):
    monkeypatch.setattr(mail_queue, "HOURLY_LIMIT", 2)
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    cid = await _assign_author("post-one", "writer")
    for i in range(4):
        cmod._submit_cooldown.clear()
        assert (await _submit(client, cid, body=f"第{i}条评论")).status_code == 200
    assert len(sent) == 2
