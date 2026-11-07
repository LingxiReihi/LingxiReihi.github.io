"""管理员「忘记密码」：随机口令 + 邮件送达 + 发不出去就不改口令。

防枚举是这里的硬要求，所以断言几乎都拿「响应 JSON 完全相同」来比对，
而不是「有没有报错」—— 报错与否本身就是信息。
"""
import json
import re

import httpx
import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User
from app.services import mail_sender, password_reset
from app.services.auth import ensure_admin

MAIL_URL = "https://mail.example.test/api/external/send"
MAIL_KEY = "FrE5XLchRI2_UtBEe7VkMWuhjPj79ACuY0iKb7zv1w0"
BOB_PASS = "bob-pass-123"


@pytest.fixture(autouse=True)
def _clear_throttle():
    password_reset._last_sent.clear()
    password_reset._sent_log.clear()
    yield


@pytest.fixture
def calls(monkeypatch):
    """替掉真发信：记录每次参数，不碰网络。"""
    recorded: list[dict] = []

    async def fake(db, *, to, subject, body_text, body_html="", transport=None):
        recorded.append({"to": to, "subject": subject, "body_text": body_text})

    monkeypatch.setattr(mail_sender, "send", fake)
    return recorded


async def _configure(client, *, override=""):
    r = await client.put("/api/v1/admin/settings/mail", json={
        "api_url": MAIL_URL, "api_key": MAIL_KEY, "override_to": override})
    assert r.status_code == 200, r.text


def _password_of(body_text: str) -> str:
    m = re.search(r"^新口令：(\S+)$", body_text, re.M)
    assert m, body_text
    return m.group(1)


async def _version(username: str) -> int:
    async with SessionLocal() as db:
        return (await db.execute(select(User.token_version).where(User.username == username))
                ).scalar_one()


async def test_forgot_password_needs_no_login(client, auth):
    await _configure(auth)
    del client.headers["Authorization"]
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == password_reset.UNIFORM_MESSAGE


async def test_unconfigured_channel_says_so_and_changes_nothing(client, auth):
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "admin"})
    assert r.json()["code"] == 50300
    assert "邮件通道" in r.json()["message"]
    assert (await client.post("/api/v1/admin/auth/login",
                              json={"username": "admin", "password": "test-pass-123"}
                              )).status_code == 200


async def test_reset_password_arrives_by_email_and_kills_old_session(client, auth, make_staff, calls):
    await _configure(auth)
    await make_staff("bob", password=BOB_PASS, email="bob@x.test")
    login = await client.post("/api/v1/admin/auth/login",
                              json={"username": "bob", "password": BOB_PASS})
    old_access = login.json()["data"]["access_token"]

    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "bob"})
    assert r.status_code == 200, r.text
    assert len(calls) == 1 and calls[0]["to"] == "bob@x.test"
    assert "bob" in calls[0]["subject"]
    new_pass = _password_of(calls[0]["body_text"])

    # 旧口令作废、旧会话下线、新口令可登录
    assert (await client.post("/api/v1/admin/auth/login",
                              json={"username": "bob", "password": BOB_PASS})).status_code == 401
    assert (await client.get("/api/v1/admin/auth/me",
                             headers={"Authorization": f"Bearer {old_access}"})).status_code == 401
    again = await client.post("/api/v1/admin/auth/login",
                              json={"username": "bob", "password": new_pass})
    assert again.status_code == 200, again.text


async def test_password_never_appears_in_the_http_response(client, auth, make_staff, calls):
    await _configure(auth)
    await make_staff("carol", password="carol-pass-123")
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "carol"})
    assert len(calls) == 1
    assert _password_of(calls[0]["body_text"]) not in r.text


async def test_send_failure_leaves_the_password_untouched(client, auth, make_staff, monkeypatch):
    await _configure(auth)
    await make_staff("dave", password="dave-pass-123")
    before = await _version("dave")

    async def failing(db, **kw):
        raise mail_sender.MailError("对端拒收")

    monkeypatch.setattr(mail_sender, "send", failing)
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "dave"})
    assert r.status_code == 200, r.text              # 不因发信失败给账号信息留线索
    assert r.json()["data"] == password_reset.UNIFORM_MESSAGE
    assert (await client.post("/api/v1/admin/auth/login",
                              json={"username": "dave", "password": "dave-pass-123"}
                              )).status_code == 200
    assert await _version("dave") == before          # 连「强制下线」都没发生 = 整笔回滚


@pytest.mark.parametrize("username", ["ghost", "no_email_admin"])
async def test_unknown_or_emailless_account_looks_exactly_like_success(
        client, auth, make_staff, calls, username):
    await _configure(auth)
    if username == "no_email_admin":
        async with SessionLocal() as db:
            await ensure_admin(db, "no_email_admin", "no-email-pass-123")
    await make_staff("erin", password="erin-pass-123")
    real = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "erin"})
    assert len(calls) == 1
    fake = await client.post("/api/v1/admin/auth/forgot-password", json={"username": username})
    assert fake.json() == real.json()                # 同一句话、同一形状，不泄露账号是否存在
    assert len(calls) == 1                           # 也没多发一封


async def test_inactive_admin_is_refused_with_the_same_words(client, auth, make_staff, calls):
    await _configure(auth)
    staff = await make_staff("frank", password="frank-pass-123")
    async with SessionLocal() as db:
        old_hash = (await db.execute(select(User).where(User.username == "frank"))).scalar_one().password_hash
    await auth.put(f"/api/v1/admin/admins/{staff['id']}", json={"is_active": False})

    await make_staff("gina", password="gina-pass-123")
    real = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "gina"})
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "frank"})
    assert r.json() == real.json()
    assert len(calls) == 1
    async with SessionLocal() as db:
        row = (await db.execute(select(User).where(User.username == "frank"))).scalar_one()
        assert row.password_hash == old_hash


async def test_second_request_inside_cooldown_sends_nothing(client, auth, make_staff, calls):
    await _configure(auth)
    await make_staff("hank", password="hank-pass-123")
    first = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "hank"})
    second = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "hank"})
    assert second.json() == first.json()
    assert len(calls) == 1


async def test_cooldown_is_per_account(client, auth, make_staff, calls):
    await _configure(auth)
    await make_staff("ivan", password="ivan-pass-123")
    await make_staff("judy", password="judy-pass-123")
    await client.post("/api/v1/admin/auth/forgot-password", json={"username": "ivan"})
    await client.post("/api/v1/admin/auth/forgot-password", json={"username": "judy"})
    assert len(calls) == 2


async def test_per_account_hourly_cap(client, auth, make_staff, calls, monkeypatch):
    monkeypatch.setattr(password_reset, "PER_ACCOUNT_HOURLY", 3)
    await _configure(auth)
    await make_staff("kim", password="kim-pass-123")
    for _ in range(6):
        r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "kim"})
        assert r.status_code == 200
        password_reset._last_sent.clear()            # 只测小时上限，绕开 60 秒冷却
    assert len(calls) == 3


async def test_global_hourly_cap_protects_the_mail_account(client, auth, make_staff, calls,
                                                           monkeypatch):
    """QQ 邮箱一小时发几十封就会被风控，全局上限是保住整条通道的关键。"""
    monkeypatch.setattr(password_reset, "GLOBAL_HOURLY", 2)
    await _configure(auth)
    for name in ("leo", "mia", "nil", "oed"):
        await make_staff(name, password=f"{name}-pass-123")
        await client.post("/api/v1/admin/auth/forgot-password", json={"username": name})
    assert len(calls) == 2


async def test_locked_account_gets_back_in_by_email(client, auth, make_staff, calls):
    await _configure(auth)
    await make_staff("nick", password="nick-pass-123")
    for _ in range(5):
        await client.post("/api/v1/admin/auth/login",
                          json={"username": "nick", "password": "wrong-wrong-wrong"})
    locked = await client.post("/api/v1/admin/auth/login",
                               json={"username": "nick", "password": "nick-pass-123"})
    assert locked.json()["code"] == 42300
    await client.post("/api/v1/admin/auth/forgot-password", json={"username": "nick"})
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "nick", "password": _password_of(calls[0]["body_text"])})
    assert r.status_code == 200, r.text


async def test_throttle_window_is_pruned_even_on_the_rejected_paths(client, auth, monkeypatch):
    """prune 必须在任何提前返回之前跑完：否则「通道未配置」会把窗口擦成一笔干净记录。"""
    import time as _t

    from app.core.crypto import encrypt_secret
    from app.models import SiteSetting
    async with SessionLocal() as db:
        await db.merge(SiteSetting(key="mail.api_url", value=MAIL_URL))
        await db.merge(SiteSetting(key="mail.api_key", value=encrypt_secret(MAIL_KEY)))
        await db.merge(SiteSetting(key="mail.override_to", value=""))
        await db.commit()
    stale = _t.monotonic() - 7200
    password_reset._sent_log.append(("kim", stale))
    password_reset._last_sent["kim"] = stale

    async def down(db, **kw):
        raise mail_sender.MailError("通道不可达")

    monkeypatch.setattr(mail_sender, "send", down)
    await client.post("/api/v1/admin/auth/forgot-password", json={"username": "ghost"})
    assert password_reset._sent_log == []
    assert "kim" not in password_reset._last_sent


async def test_cooldown_state_stays_bounded(client, auth, make_staff, calls):
    """只有真发过信的账号才留在冷却表里，且过期条目会被逐出（防无界增长）。"""
    import time as _t

    await _configure(auth)
    password_reset._last_sent["ghost"] = _t.monotonic() - 7200
    await make_staff("paul", password="paul-pass-123")
    await client.post("/api/v1/admin/auth/forgot-password", json={"username": "paul"})
    assert "ghost" not in password_reset._last_sent
    assert "paul" in password_reset._last_sent


async def test_forgot_password_honors_the_override_recipient(client, auth, make_staff, monkeypatch):
    """测试收件人非空时重置邮件改投它（线上留空），这里走真 mail_sender、只换传输层。"""
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    mock, orig = httpx.MockTransport(handler), httpx.AsyncClient
    monkeypatch.setattr(mail_sender.httpx, "AsyncClient", lambda **kw: orig(transport=mock))
    await _configure(auth, override="orihiya@foxmail.com")
    await make_staff("olive", password="olive-pass-123")
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "olive"})
    assert r.status_code == 200, r.text
    assert seen and seen[0]["to"] == ["orihiya@foxmail.com"]


async def test_reset_mail_is_queued_never_but_records_budget(client, auth, make_staff, calls):
    """口令信**不入队**（明文不能在库里等下一小时），但要记一条无正文的台账占额度，
    否则「全站一份总预算」对重置这条链路就是空话。"""
    await _configure(auth)
    await make_staff("quinn", password="quinn-pass-123")
    assert (await client.post("/api/v1/admin/auth/forgot-password",
                              json={"username": "quinn"})).status_code == 200
    from app.models import MailQueue
    async with SessionLocal() as db:
        rows = (await db.execute(select(MailQueue))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "sent" and rows[0].kind == "forgot_password"
    assert rows[0].body_text == ""                  # 台账不含正文，明文口令不落库
    assert calls and "新口令" in calls[0]["body_text"]


async def test_exhausted_budget_refuses_reset_and_keeps_old_password(
        client, auth, make_staff, monkeypatch):
    from app.services import mail_queue
    monkeypatch.setattr(mail_queue, "HOURLY_LIMIT", 0)
    await _configure(auth)
    await make_staff("rosa", password="rosa-pass-123")
    r = await client.post("/api/v1/admin/auth/forgot-password", json={"username": "rosa"})
    assert r.json()["code"] == 50300 and "额度" in r.json()["message"]
    assert (await client.post("/api/v1/admin/auth/login",
                              json={"username": "rosa", "password": "rosa-pass-123"}
                              )).status_code == 200
