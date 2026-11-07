"""配置项的静态加密：库里只存 Fernet 密文，主密钥由 .env 里的 jwt_secret 派生。

不新增 env 项的理由：HKDF 派生让「拿到 app.db 或其备份」的人看不到发信凭据，
而 .env 本来就是本站最高凭据（jwt_secret）的存放处，不必再多一把要人记的钥匙。
jwt_secret 一变，旧密文就解不开 —— 届时后台会显示「未配置」，重填一次即可。
"""
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import settings

_INFO = b"personal-web-settings-secret"


def _fernet() -> Fernet:
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=_INFO).derive(settings.jwt_secret.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(value: str) -> str:
    value = (value or "").strip()
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt_secret(blob: object) -> str:
    """解不开一律当「没配」—— 绝不能把乱码当凭据发给外部服务。"""
    if not blob:
        return ""
    try:
        return _fernet().decrypt(str(blob).encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return ""
