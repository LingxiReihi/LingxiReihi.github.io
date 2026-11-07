import jwt as pyjwt
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..core.deps import get_current_admin
from ..core.errors import AppException, ErrorCode, ok
from ..core.logs import log_event
from ..models import User
from ..schemas.auth import ForgotReq, LoginReq, PasswordReq, RefreshReq
from ..services import auth as auth_svc
from ..services import password_reset

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "-"


@router.post("/login")
async def login(body: LoginReq, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        access, refresh, user = await auth_svc.login(db, body.username, body.password)
    except AppException:
        log_event("auth", f"登录失败 username={body.username} ip={_ip(request)}", level="warning")
        raise
    log_event("auth", f"登录成功 username={user.username} ip={_ip(request)}")
    from ..core.config import settings
    return ok({
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": settings.access_token_minutes * 60,
        "user": await auth_svc.user_out(db, user),
    })


@router.post("/forgot-password")
async def forgot_password(body: ForgotReq, request: Request, db: AsyncSession = Depends(get_db)):
    """免鉴权自助重置：新口令只进邮件，响应永远是同一句话（防枚举口径见 password_reset）。"""
    try:
        await password_reset.request(db, body.username)
    except AppException as e:
        log_event("auth", f"忘记密码被拒 username={body.username} ip={_ip(request)} "
                          f"reason={e.message}", level="warning")
        raise
    log_event("auth", f"忘记密码已受理 username={body.username} ip={_ip(request)}")
    # 话术放 data：前端 api() 只透传 data，措辞由服务端持有（防枚举口径不能各处复制）
    return ok(password_reset.UNIFORM_MESSAGE)


@router.post("/refresh")
async def refresh(body: RefreshReq, db: AsyncSession = Depends(get_db)):
    access, refresh = await auth_svc.refresh_tokens(db, body.refresh_token)
    from ..core.config import settings
    return ok({"access_token": access, "refresh_token": refresh,
               "expires_in": settings.access_token_minutes * 60})


@router.post("/logout")
async def logout(user: User = Depends(get_current_admin)):
    # v1 无黑名单：refresh 旋转 + exp 自然失效，服务端仅记录
    log_event("auth", "登出", actor=user.username)
    return ok()


@router.get("/me")
async def me(user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return ok(await auth_svc.user_out(db, user))


from ..core.errors import ok


@router.post("/password")
async def password(body: PasswordReq, user: User = Depends(get_current_admin),
                   db: AsyncSession = Depends(get_db)):
    await auth_svc.change_password(db, user, body.old_password, body.new_password)
    log_event("auth", "修改密码", actor=user.username)
    return ok(message="密码已更新，请重新登录")
