"""邮件通道设置（mail 组）与忘记密码（发随机口令）。

口径（2026-10-06 拍板）：
- api_key 存 site_settings.mail.api_key，任何读接口都不回明文，只回「是否已配 + 尾号」；
- 保存时留空 = 保留原 key（否则前端掩码回显会把凭据洗掉）；
- 发不出去就绝不改口令（写库→发信→成功才 commit / 失败 rollback）。
"""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import SiteSetting


async def _mail_rows() -> dict:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(SiteSetting).where(SiteSetting.key.like("mail.%")))).scalars().all()
        return {r.key.split(".", 1)[1]: r.value for r in rows}


MAIL_BODY = {"api_url": "http://mail:8000/api/external/send",
             "api_key": "FrE5XLchRI2_UtBEe7VkMWuhjPj79ACuY0iKb7zv1w0",
             "override_to": "orihiya@foxmail.com"}


async def test_mail_group_roundtrip_without_plaintext_key(auth):
    r = await auth.put("/api/v1/admin/settings/mail", json=MAIL_BODY)
    assert r.status_code == 200, r.text
    body = r.json()["data"]["mail"]
    assert MAIL_BODY["api_key"] not in str(body)
    assert body["api_key_set"] is True
    assert body["api_key_hint"] == MAIL_BODY["api_key"][-4:]
    assert body["api_url"] == MAIL_BODY["api_url"]
    # 落库的必须是密文：库文件和上线前的备份都会被搬来搬去，不能等于凭据本身
    stored = (await _mail_rows())["api_key"]
    assert stored != MAIL_BODY["api_key"] and MAIL_BODY["api_key"] not in str(stored)
    from app.core.crypto import decrypt_secret
    assert decrypt_secret(stored) == MAIL_BODY["api_key"]

    got = (await auth.get("/api/v1/admin/settings")).json()["data"]["mail"]
    assert MAIL_BODY["api_key"] not in str(got)
    assert got["api_key_set"] is True


async def test_blank_key_on_save_keeps_the_stored_key(auth):
    await auth.put("/api/v1/admin/settings/mail", json=MAIL_BODY)
    r = await auth.put("/api/v1/admin/settings/mail", json={
        "api_url": "https://mail.lingxi-reihi.cn/api/external/send", "api_key": "", "override_to": ""})
    assert r.status_code == 200, r.text
    from app.core.crypto import decrypt_secret
    assert decrypt_secret((await _mail_rows())["api_key"]) == MAIL_BODY["api_key"]
    assert (await _mail_rows())["api_url"] == "https://mail.lingxi-reihi.cn/api/external/send"
    assert r.json()["data"]["mail"]["api_key_set"] is True


async def test_saving_a_new_key_rotates_it(auth):
    await auth.put("/api/v1/admin/settings/mail", json=MAIL_BODY)
    await auth.put("/api/v1/admin/settings/mail", json={**MAIL_BODY, "api_key": "brand-new-key-9"})
    from app.core.crypto import decrypt_secret
    assert decrypt_secret((await _mail_rows())["api_key"]) == "brand-new-key-9"


async def test_undecryptable_key_counts_as_unconfigured(auth):
    """jwt_secret 变更后密文解不开：当成没配，宁可报通道未就绪也不能把乱码当凭据发出去。"""
    from app.core.crypto import decrypt_secret
    async with SessionLocal() as db:
        await db.merge(SiteSetting(key="mail.api_key", value="gAAAAA旧密钥留下的密文或手工塞的乱码"))
        await db.merge(SiteSetting(key="mail.api_url", value=MAIL_BODY["api_url"]))
        await db.commit()
    assert decrypt_secret((await _mail_rows())["api_key"]) == ""
    mail = (await auth.get("/api/v1/admin/settings")).json()["data"]["mail"]
    assert mail["api_key_set"] is False and mail["api_key_hint"] == ""
    r = await auth.post("/api/v1/admin/auth/forgot-password", json={"username": "admin"})
    assert r.json()["code"] == 50300


async def test_derived_fields_are_never_persisted(auth):
    """前端把掩码回显对象原样 PUT 回来时，不得写出 mail.api_key_set 这类假设置行。"""
    data = (await auth.put("/api/v1/admin/settings/mail", json=MAIL_BODY)).json()["data"]["mail"]
    await auth.put("/api/v1/admin/settings/mail", json=data)
    assert set(await _mail_rows()) == {"api_url", "api_key", "override_to"}


async def test_mail_group_is_not_in_public_config(auth, client):
    await auth.put("/api/v1/admin/settings/mail", json=MAIL_BODY)
    cfg = await client.get("/api/v1/site-config")
    assert MAIL_BODY["api_key"] not in cfg.text
    assert "mail.lingxi" not in cfg.text and "api_key" not in cfg.text
    assert "mail" not in cfg.json()["data"]


async def test_mail_group_write_still_needs_setting_manage(client, auth, make_staff):
    await make_staff("staff_mail")
    from tests.test_ownership import _login_as   # 既有换身份助手，别再造一份
    await _login_as(client, "staff_mail")
    r = await client.put("/api/v1/admin/settings/mail", json=MAIL_BODY)
    assert r.json()["code"] == 40300
    assert await _mail_rows() == {}


# ---------- mail_sender：同服务器 personal-mail 的 /api/external/send ----------
import json  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.services import mail_sender  # noqa: E402

SEND_URL = "https://mail.example.test/api/external/send"


@pytest.fixture
def sent():
    """把 mail_sender 指到 MockTransport，记录每一次出站请求。"""
    calls: list[httpx.Request] = []

    def _use(handler):
        def _handler(request: httpx.Request) -> httpx.Request:
            calls.append(request)
            return handler(request)
        return httpx.MockTransport(_handler), calls
    return _use


async def _send(transport, *, to="someone@x.test", url=SEND_URL, key="k-secret-abcd",
                override=""):
    from app.core.crypto import encrypt_secret
    async with SessionLocal() as db:
        for k, v in (("api_url", url), ("api_key", encrypt_secret(key)), ("override_to", override)):
            await db.merge(SiteSetting(key=f"mail.{k}", value=v))
        await db.commit()
        await mail_sender.send(db, to=to, subject="口令重置", body_text="新口令：abc123",
                               transport=transport)


async def test_send_posts_bearer_key_and_plain_text_only(sent):
    transport, calls = sent(lambda r: httpx.Response(200, json={"ok": True, "data": {}}))
    await _send(transport)
    assert len(calls) == 1
    req = calls[0]
    assert req.headers["Authorization"] == "Bearer k-secret-abcd"
    body = json.loads(req.content)
    assert body == {"to": ["someone@x.test"], "subject": "口令重置", "body_text": "新口令：abc123"}
    assert "draft_id" not in body   # 外部端点带 draft_id 会被对端 400


async def test_override_to_redirects_every_message(sent):
    transport, calls = sent(lambda r: httpx.Response(200, json={"ok": True}))
    await _send(transport, to="owner@x.test", override="orihiya@foxmail.com")
    body = json.loads(calls[0].content)
    assert body["to"] == ["orihiya@foxmail.com"]


async def test_override_equal_to_recipient_is_not_rewritten(sent):
    transport, calls = sent(lambda r: httpx.Response(200, json={"ok": True}))
    await _send(transport, to="orihiya@foxmail.com", override="orihiya@foxmail.com")
    body = json.loads(calls[0].content)
    assert body["to"] == ["orihiya@foxmail.com"]


@pytest.mark.parametrize("status,payload,expect", [
    (403, {"ok": False, "error": {"code": "EXTERNAL_DISABLED", "message": "disabled"}}, "未就绪"),
    (401, {"ok": False, "error": {"code": "EXTERNAL_UNAUTHORIZED", "message": "bad key"}}, "凭据"),
    (502, {"ok": False, "error": {"code": "SEND_REJECTED", "message": "rejected"}}, "拒收"),
    (500, {"not": "json"}, "500"),
])
async def test_error_responses_become_mail_error(sent, status, payload, expect):
    transport, _ = sent(lambda r: httpx.Response(status, json=payload))
    with pytest.raises(mail_sender.MailError) as e:
        await _send(transport)
    assert expect in str(e.value)


async def test_network_failure_becomes_mail_error(sent):
    def boom(_r):
        raise httpx.ConnectTimeout("timeout")
    transport, _ = sent(boom)
    with pytest.raises(mail_sender.MailError):
        await _send(transport)


async def test_ok_false_with_200_is_still_failure(sent):
    transport, _ = sent(lambda r: httpx.Response(200, json={
        "ok": False, "error": {"code": "SEND_AUTH_FAILED", "message": "授权码失效"}}))
    with pytest.raises(mail_sender.MailError) as e:
        await _send(transport)
    assert "授权" in str(e.value)


async def test_mail_config_prefers_db_over_env(sent, monkeypatch):
    monkeypatch.setattr(mail_sender.settings, "mail_api_url", "http://env-host/x")
    monkeypatch.setattr(mail_sender.settings, "mail_api_key", "env-key")
    transport, calls = sent(lambda r: httpx.Response(200, json={"ok": True}))
    await _send(transport, url="http://db-host/x", key="db-key")
    assert str(calls[0].url) == "http://db-host/x"
    assert calls[0].headers["Authorization"] == "Bearer db-key"


async def test_mail_config_falls_back_to_env(sent):
    async with SessionLocal() as db:
        await db.execute(delete(SiteSetting))
        await db.commit()
        cfg = await mail_sender.mail_config(db)
    assert cfg["url"] == mail_sender.settings.mail_api_url
    assert cfg["key"] == mail_sender.settings.mail_api_key


def test_channel_is_not_ready_without_url_or_key():
    assert mail_sender.channel_ready({"url": SEND_URL, "key": "k", "override_to": ""}) is True
    assert mail_sender.channel_ready({"url": SEND_URL, "key": "", "override_to": ""}) is False
    assert mail_sender.channel_ready({"url": "", "key": "k", "override_to": ""}) is False

