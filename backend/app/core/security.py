from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

JWT_ALG = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, token_type: str, token_version: int) -> str:
    now = datetime.now(timezone.utc)
    if token_type == "refresh":
        exp = now + timedelta(days=settings.refresh_token_days)
    else:
        exp = now + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user_id), "type": token_type, "tv": token_version, "iat": now, "exp": exp}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses on invalid/expired token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
