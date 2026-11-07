from dataclasses import dataclass

import jwt
from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .errors import AppException, ErrorCode
from .security import decode_token
from ..models import User


async def get_current_admin(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AppException(ErrorCode.UNAUTHORIZED, "未登录")
    try:
        payload = decode_token(header[7:])
    except jwt.ExpiredSignatureError:
        raise AppException(ErrorCode.UNAUTHORIZED, "token 已过期")
    except jwt.PyJWTError:
        raise AppException(ErrorCode.UNAUTHORIZED, "token 无效")
    if payload.get("type") != "access":
        raise AppException(ErrorCode.UNAUTHORIZED, "token 类型错误")
    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise AppException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录")
    if not user.is_active:
        raise AppException(ErrorCode.UNAUTHORIZED, "账号已停用")
    if user.token_version != payload.get("tv"):
        raise AppException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录")
    return user


GrantKey = tuple[str, str, int | None]      # (permission, scope_type, scope_id)


async def fetch_grants(db: AsyncSession, user_id: int) -> frozenset[GrantKey]:
    from ..models import AdminGrant
    rows = (await db.execute(
        select(AdminGrant.permission, AdminGrant.scope_type, AdminGrant.scope_id)
        .where(AdminGrant.user_id == user_id))).all()
    return frozenset(rows)


@dataclass
class AdminContext:
    """一次请求的权限视图。super 隐式全有、不落库。"""
    user: User
    is_super: bool
    grants: frozenset[GrantKey]

    def can(self, perm: str, *, column_id: int | None = None) -> bool:
        if self.is_super:
            return True
        if (perm, "global", None) in self.grants:
            return True
        return column_id is not None and (perm, "column", column_id) in self.grants

    @property
    def permissions(self) -> list[str]:
        from .permissions import PERMISSIONS
        if self.is_super:
            return sorted(PERMISSIONS)
        return sorted({p for p, _scope, _sid in self.grants})

    @property
    def scoped_column_ids(self) -> list[int]:
        if self.is_super:
            return []
        return sorted({sid for _p, scope, sid in self.grants if scope == "column" and sid is not None})

    # ---- 判定与拒绝：文案区分「没这个权限」与「没有这个栏目的权限」与「不是你的内容」 ----

    def need(self, perm: str, *, subject: str = "管理") -> None:
        """要求全局权限点（无栏目维度）。"""
        if not self.can(perm):
            raise AppException(ErrorCode.FORBIDDEN, f"你没有{subject}权限")

    def need_scoped(self, perm: str, *, column_id: int | None,
                          column_name: str | None = None, subject: str = "内容管理") -> None:
        if self.can(perm, column_id=column_id):
            return
        if column_id is None:
            raise AppException(ErrorCode.FORBIDDEN, f"未挂栏目需要全局{subject}权限")
        raise AppException(ErrorCode.FORBIDDEN, f"你没有栏目「{column_name or column_id}」的{subject}权限")

    def need_owner(self, owner_id: int | None, *, owner_name: str | None = None,
                   subject: str = "该内容") -> None:
        if self.is_super or owner_id == self.user.id:
            return
        if owner_id is None:
            raise AppException(ErrorCode.FORBIDDEN, f"{subject}无归属，只有顶级管理员可管理")
        raise AppException(ErrorCode.FORBIDDEN,
                           f"{subject}由 {owner_name or '其他管理员'} 创建，你只能管理自己上传的内容")

    def can_edit_content(self, c, *, need_delete: bool = False) -> bool:
        if self.is_super:
            return True
        if c.created_by_id != self.user.id:
            return False
        if not self.can("content:write", column_id=c.column_id):
            return False
        return not need_delete or self.can("content:delete", column_id=c.column_id)

    def content_denied_reason(self, c, *, need_delete: bool = False) -> str | None:
        if self.can_edit_content(c, need_delete=need_delete):
            return None
        if self.is_super:
            return None
        if c.created_by_id != self.user.id:
            name = c.created_by.nickname if c.created_by else None
            return (f"该内容无归属，只有顶级管理员可管理" if c.created_by_id is None
                    else f"该内容由 {name or '其他管理员'} 创建，你只能管理自己上传的内容")
        if not self.can("content:write", column_id=c.column_id):
            return "未挂栏目需要全局内容管理权限" if c.column_id is None else "你没有该栏目的内容管理权限"
        return "你没有内容删除权限" if need_delete else None


async def build_ctx(db: AsyncSession, user: User) -> AdminContext:
    """由 user 组装权限视图（super 不查 grant 表）。"""
    grants = frozenset() if user.is_super else await fetch_grants(db, user.id)
    return AdminContext(user=user, is_super=user.is_super, grants=grants)


async def get_admin_ctx(request: Request, db: AsyncSession = Depends(get_db)) -> AdminContext:
    """权限实时读库：撤权/停用/改 role 下一次请求即生效，不等 token 过期。"""
    user = await get_current_admin(request, db)
    return await build_ctx(db, user)


@dataclass
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_page(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def parse_day_params(start: str | None, end: str | None, default_days: int = 7) -> tuple[int, int]:
    """YYYY-MM-DD 或 YYYYMMDD；缺省近 default_days 天。"""
    from datetime import datetime, timedelta, timezone

    def norm(s: str) -> int:
        return int(s.replace("-", ""))

    if end is None or start is None:
        e_dt = datetime.now(timezone.utc)
        s_dt = e_dt - timedelta(days=default_days - 1)
        return int(s_dt.strftime("%Y%m%d")), int(e_dt.strftime("%Y%m%d"))
    s, e = norm(start), norm(end)
    if not (20000101 <= s <= e <= 21000101):
        raise AppException(ErrorCode.BAD_REQUEST, "日期范围无效")
    if e - s > 400:
        raise AppException(ErrorCode.BAD_REQUEST, "范围超过 366 天")
    return s, e
