from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.errors import AppException, ErrorCode
from ..core.security import create_token, hash_password, verify_password
from ..models import User

MAX_FAILED = 5
LOCK_MINUTES = 10


async def get_user_by_name(db: AsyncSession, username: str) -> User | None:
    return (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()


async def login(db: AsyncSession, username: str, password: str) -> tuple[str, str, User]:
    user = await get_user_by_name(db, username)
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until > now:
        retry = int((user.locked_until - now).total_seconds())
        raise AppException(ErrorCode.LOCKED, "失败次数过多，账号已临时锁定",
                           data={"retry_after": max(retry, 1)})
    if not user or not verify_password(password, user.password_hash):
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= MAX_FAILED:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_attempts = 0
        await db.commit()
        raise AppException(ErrorCode.BAD_CREDENTIALS, "账号或密码错误")
    user.failed_attempts = 0
    user.locked_until = None
    if not user.is_active:
        await db.commit()
        raise AppException(ErrorCode.UNAUTHORIZED, "账号已停用，请联系顶级管理员")
    user.last_login_at = now
    access = create_token(user.id, "access", user.token_version)
    refresh = create_token(user.id, "refresh", user.token_version)
    await db.commit()
    return access, refresh, user


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    import jwt as pyjwt
    from ..core.security import decode_token
    try:
        payload = decode_token(refresh_token)
    except pyjwt.PyJWTError:
        raise AppException(ErrorCode.UNAUTHORIZED, "refresh token 无效或已过期")
    if payload.get("type") != "refresh":
        raise AppException(ErrorCode.UNAUTHORIZED, "token 类型错误")
    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise AppException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录")
    # 停用判定放在 token_version 之前：停用会 bump 版本，否则用户只看到含糊的「登录已失效」
    if not user.is_active:
        raise AppException(ErrorCode.UNAUTHORIZED, "账号已停用")
    if user.token_version != payload.get("tv"):
        raise AppException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录")
    # refresh 旋转：旧 token 随 exp 自然失效，签发新对
    return (create_token(user.id, "access", user.token_version),
            create_token(user.id, "refresh", user.token_version))


async def change_password(db: AsyncSession, user: User, old: str, new: str) -> None:
    if not verify_password(old, user.password_hash):
        raise AppException(ErrorCode.BAD_CREDENTIALS, "旧密码错误")
    user.password_hash = hash_password(new)
    user.token_version += 1   # 全端失效，需重新登录
    await db.commit()


async def ensure_admin(db: AsyncSession, username: str, password: str, nickname: str = "") -> User | None:
    """幂等 seed：存在则返回 None，不存在则创建为顶级管理员。"""
    if await get_user_by_name(db, username):
        return None
    user = User(username=username, password_hash=hash_password(password),
                nickname=nickname or username, role="super")
    db.add(user)
    await db.commit()
    return user


async def user_out(db: AsyncSession, user: User) -> dict:
    """登录/me 的账号载荷：附带权限集合，前端据此渲染菜单与按钮（后端仍是唯一安全边界）。"""
    from ..core.deps import build_ctx
    ctx = await build_ctx(db, user)
    return {
        "id": user.id, "username": user.username, "nickname": user.nickname,
        "role": user.role, "is_super": ctx.is_super, "is_active": user.is_active,
        "permissions": ctx.permissions, "scoped_column_ids": ctx.scoped_column_ids,
    }
