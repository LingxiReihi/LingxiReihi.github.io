"""评论首次审核通过 → 通知评论者本人。

去重靠 comments.notified_at 这个持久列，而不是「队列里有没有行」：
所以「通过 → 拒绝 → 再通过」也只发一封，重启或队列被清空都不会重发。
"""
import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Comment, MailQueue
from app.services import mail_queue, mail_sender
from tests.test_comment_notify import _assign_author, _content_id, _submit
from tests.test_public import seed_contents  # noqa: F401


@pytest.fixture(autouse=True)
def _clear_cooldown():
    # 提交冷却是进程内 dict，跨用例会累积成 429（同 test_comment_notify 的处理）
    from app.api import comments as cmod
    cmod._submit_cooldown.clear()
    yield


@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    monkeypatch.setattr(mail_sender, "channel_ready", lambda cfg: True)
    calls: list[dict] = []

    async def fake(db, *, to, subject, body_text, body_html="", transport=None):
        calls.append({"to": to, "subject": subject, "body_text": body_text})

    monkeypatch.setattr(mail_sender, "send", fake)
    return calls


async def _pending_comment_id(client, slug: str = "post-one") -> int:
    cid = await _content_id(client, slug)
    assert (await _submit(client, cid)).status_code == 200
    async with SessionLocal() as db:
        return (await db.execute(select(Comment))).scalars().first().id


async def _approve(auth, ids: list[int], status: str = "approved"):
    return await auth.post("/api/v1/admin/comments/moderate", json={"ids": ids, "status": status})


async def _comment(id_: int) -> Comment:
    async with SessionLocal() as db:
        return await db.get(Comment, id_)


async def test_first_approval_notifies_the_commenter(client, auth, make_staff, _ready):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    await _assign_author("post-one", "writer")
    c_id = await _pending_comment_id(client)
    _ready.clear()                                  # 只留审核阶段的出信
    assert (await _approve(auth, [c_id])).json()["data"]["updated"] == 1
    assert [c["to"] for c in _ready] == ["xiaoming@example.com"]     # 发给评论者，不是作者
    assert (await _comment(c_id)).notified_at is not None


async def test_approving_twice_does_not_resend(client, auth, make_staff, _ready):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    await _assign_author("post-one", "writer")
    c_id = await _pending_comment_id(client)
    _ready.clear()
    await _approve(auth, [c_id])
    await _approve(auth, [c_id])                    # 再点一次「通过」
    assert len(_ready) == 1


async def test_reject_then_reapprove_sends_only_one(client, auth, make_staff, _ready):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    await _assign_author("post-one", "writer")
    c_id = await _pending_comment_id(client)
    _ready.clear()
    await _approve(auth, [c_id], status="rejected")
    assert _ready == []                             # 拒绝不发信
    await _approve(auth, [c_id])                    # 反悔再通过 → 这才算首次
    await _approve(auth, [c_id], status="rejected")
    await _approve(auth, [c_id])                    # 再通过不重发
    assert len(_ready) == 1


async def test_batch_approval_notifies_each_commenter(client, auth, make_staff, _ready):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    await _assign_author("post-one", "writer")
    cid = await _content_id(client, "post-one")
    ids = []
    for i, mail in enumerate(("a@x.test", "b@x.test", "c@x.test")):
        from app.api import comments as cmod
        cmod._submit_cooldown.clear()
        await _submit(client, cid, email=mail, nickname=f"访客{i}", body=f"第{i}条")
        async with SessionLocal() as db:
            ids.append((await db.execute(select(Comment).where(Comment.email == mail)))
                       .scalars().one().id)
    _ready.clear()
    assert (await _approve(auth, ids)).json()["data"]["updated"] == 3
    assert sorted(c["to"] for c in _ready) == ["a@x.test", "b@x.test", "c@x.test"]


async def test_visitor_mail_carries_title_link_and_own_text(client, auth, make_staff, _ready):
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    await _assign_author("post-one", "writer")
    c_id = await _pending_comment_id(client)
    _ready.clear()
    await _approve(auth, [c_id])
    mail = _ready[0]
    assert "第一篇文章" in mail["subject"]
    body = mail["body_text"]
    assert "写得好！" in body and "/blog/post-one" in body and "小明" in body
    assert "writer@x.test" not in body              # 不把作者邮箱塞给访客


async def test_visitor_notice_is_queued_not_sent_inline(client, auth, make_staff, _ready):
    """审核响应不该等 SMTP：入队与 notified_at 同一笔事务，出信由 drain 顺带跑。"""
    await seed_contents()
    await make_staff("writer", email="writer@x.test")
    await _assign_author("post-one", "writer")
    c_id = await _pending_comment_id(client)
    _ready.clear()
    await _approve(auth, [c_id])
    async with SessionLocal() as db:
        rows = (await db.execute(select(MailQueue).where(MailQueue.kind == "comment_visitor")))
    visitor = rows.scalars().all()                 # 作者信是另一行（提交时入队），这里只看访客信
    assert len(visitor) == 1
    assert visitor[0].status in ("sent", "pending")    # 顺带冲刷成功，或被额度/退避延后
