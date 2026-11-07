"""配置密钥静态加密：库里只存 Fernet 密文，主密钥由 .env 的 jwt_secret 派生。"""
from app.core import crypto


def test_roundtrip_and_ciphertext_differs_each_time():
    key = "FrE5XLchRI2_UtBEe7VkMWuhjPj79ACuY0iKb7zv1w0"
    a, b = crypto.encrypt_secret(key), crypto.encrypt_secret(key)
    assert a != b                       # 带时间戳/随机 IV，同明文两次密文不同
    assert key not in a and key not in b
    assert crypto.decrypt_secret(a) == key
    assert crypto.decrypt_secret(b) == key


def test_garbage_or_empty_decrypts_to_nothing():
    for bad in ("", None, "gAAAAA明显不是合法token", "随手贴进来的明文"):
        assert crypto.decrypt_secret(bad) == ""


def test_key_is_derived_from_jwt_secret(monkeypatch):
    from app.core.config import settings
    blob = crypto.encrypt_secret("abcdef123456")
    monkeypatch.setattr(settings, "jwt_secret", "another-secret-entirely")
    assert crypto.decrypt_secret(blob) == ""


def test_blank_value_is_stored_blank_not_encrypted():
    assert crypto.encrypt_secret("") == ""
    assert crypto.encrypt_secret("   ") == ""
