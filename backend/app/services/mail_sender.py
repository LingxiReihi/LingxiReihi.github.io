"""同服务器 personal-mail 的外部发信 API（POST /api/external/send，Bearer Key 鉴权）。

失败一律抛 MailError，绝不静默 —— 调用方据此保证「发不出去就不改口令」。
配置优先读后台「站点设置 → 邮件通道」（site_settings.mail.*，其中 api_key 是密文），
解不出则回落 .env。
"""
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.crypto import decrypt_secret
from ..core.logs import log_event
from .settings import get_group

TIMEOUT_SECONDS = 15

# 对端错误码 → 人话（docs/external-api.md 的错误表）
_REASON = {
    "EXTERNAL_DISABLED": "邮件通道未就绪（发信服务未启用外部接口）",
    "EXTERNAL_UNAUTHORIZED": "邮件通道凭据无效，请在站点设置里重新填写 API Key",
    "BAD_REQUEST": "发信请求不合法",
    "SEND_MESSAGE_INVALID": "邮件内容不合法",
    "SEND_AUTH_FAILED": "发信账号登录失败（邮箱授权码已失效）",
    "SEND_REJECTED": "邮件被投递服务器拒收",
    "SEND_TOO_MANY": "发信过于频繁，请稍后再试",
    "SEND_MESSAGE_TOO_LARGE": "邮件正文过长",
    "SEND_CONNECTION_FAILED": "发信服务连不上邮箱服务器",
}


class MailError(Exception):
    """一封都没发出去。口令重置流程据此回滚。"""


async def mail_config(db: AsyncSession) -> dict:
    g = await get_group(db, "mail")

    def pick(field: str, fallback: str) -> str:
        return str(g.get(field) or "").strip() or fallback

    # 库里的 api_key 是密文；解不开就当没配。只有 .env 兜底那条路存明文
    key = decrypt_secret(g.get("api_key")) or settings.mail_api_key.strip()
    return {"url": pick("api_url", settings.mail_api_url),
            "key": key,
            "override_to": pick("override_to", settings.mail_override_to)}


def channel_ready(cfg: dict) -> bool:
    return bool(cfg.get("url") and cfg.get("key"))


def _reason(status: int, code: str) -> str:
    return _REASON.get(code) or f"邮件服务返回 {status}" + (f"（{code}）" if code else "")


async def send(db: AsyncSession, *, to: str, subject: str, body_text: str,
               body_html: str = "",
               transport: httpx.AsyncBaseTransport | None = None) -> None:
    """发一封信。body_html 非空时对端会发 multipart/alternative（纯文本兜底 + HTML 正文）。
    transport 是测试注入口（httpx.MockTransport）。"""
    cfg = await mail_config(db)
    if not channel_ready(cfg):
        raise MailError("邮件通道未配置")
    recipients = [to]
    override = cfg["override_to"]
    if override and override.lower() != to.lower():
        # 收件人改写只该出现在测试环境，所以每次都用 warning 档留痕
        log_event("mail", f"测试收件人改写 {to} → {override}", level="warning")
        recipients = [override]
    kw = {"transport": transport} if transport is not None else {}
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, trust_env=False, **kw) as client:
        try:
            payload_in = {"to": recipients, "subject": subject, "body_text": body_text}
            if body_html:
                payload_in["body_html"] = body_html
            r = await client.post(cfg["url"], headers={"Authorization": f"Bearer {cfg['key']}"},
                                  json=payload_in)
        except httpx.HTTPError as e:
            raise MailError(f"邮件通道不可达：{type(e).__name__}") from e
    try:
        payload = r.json() if r.content else {}
    except ValueError:
        payload = {}
    code = str((payload.get("error") or {}).get("code") or "") if isinstance(payload, dict) else ""
    refused = isinstance(payload, dict) and payload.get("ok") is False
    if r.status_code >= 400 or refused or not isinstance(payload, dict):
        raise MailError(_reason(r.status_code, code))
    log_event("mail", f"发信成功 to={recipients[0]} subject={subject}")
