"""管理员账号与授权的服务层（路由保持薄）。"""
import secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import AppException, ErrorCode
from ..core.permissions import PERMISSIONS, SCOPED_PERMISSIONS
from ..core.security import hash_password
from ..models import AdminGrant, Content, MediaAsset, User
from . import profiles as profile_svc

MIN_PASSWORD_LEN = 10
ROLE_SUPER = "super"
ROLE_STAFF = "staff"
# 代改他人时可用的资料字段：与 profiles 的白名单同源（昵称走自己的守卫分支），
# 免得两处各列一份、改一边忘另一边
PROFILE_KEYS = tuple(k for k in profile_svc.EDITABLE_FIELDS if k != "nickname")
_PW_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def norm_email(email: str) -> str:
    """存前归一为小写去空格，避免 Alice@X 与 alice@x 绕过唯一约束。"""
    return (email or "").strip().lower()


async def _ensure_email_free(db: AsyncSession, email: str, *, exclude_id: int | None = None) -> str:
    norm = norm_email(email)
    if not norm or "@" not in norm or "." not in norm.split("@")[-1]:
        raise AppException(ErrorCode.VALIDATION, "邮箱格式无效")
    q = select(User.id, User.username).where(User.email == norm)
    if exclude_id is not None:
        q = q.where(User.id != exclude_id)
    taken = (await db.execute(q.limit(1))).first()
    if taken:
        raise AppException(ErrorCode.CONFLICT, f"邮箱已被「{taken[1]}」使用")
    return norm


def check_password_strength(password: str) -> None:
    """至少 10 位且同时含字母与数字；否则 422。"""
    if (len(password) < MIN_PASSWORD_LEN
            or not any(c.isalpha() for c in password)
            or not any(c.isdigit() for c in password)):
        raise AppException(ErrorCode.VALIDATION,
                           f"口令至少 {MIN_PASSWORD_LEN} 位且需同时含字母与数字")


def gen_password(length: int = 16) -> str:
    """重置口令：保证含字母与数字（满足自身强度规则）。"""
    while True:
        pw = "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))
        if any(c.isdigit() for c in pw):
            return pw


def normalize_grants(items: list[dict]) -> set[tuple[str, str, int | None]]:
    """把 API 形态 [{permission, column_id}] 校验并转成 (permission, scope_type, scope_id) 集合。"""
    out: set[tuple[str, str, int | None]] = set()
    for raw in items or []:
        perm = raw.get("permission")
        column_id = raw.get("column_id")
        if perm not in PERMISSIONS:
            raise AppException(ErrorCode.BAD_REQUEST, f"未知权限点「{perm}」")
        if column_id is None:
            out.add((perm, "global", None))
            continue
        if perm not in SCOPED_PERMISSIONS:
            raise AppException(ErrorCode.BAD_REQUEST,
                               f"权限点「{perm}」不支持按栏目授权，只能授全局")
        out.add((perm, "column", int(column_id)))
    return out


async def get_or_404(db: AsyncSession, admin_id: int) -> User:
    user = await db.get(User, admin_id)
    if not user:
        raise AppException(ErrorCode.NOT_FOUND, "管理员不存在")
    return user


async def _active_super_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(User).where(
        User.role == ROLE_SUPER, User.is_active.is_(True)))).scalar_one()


async def _grant_rows(db: AsyncSession, user_ids: list[int]) -> dict[int, list[dict]]:
    if not user_ids:
        return {}
    rows = (await db.execute(select(AdminGrant).where(AdminGrant.user_id.in_(user_ids))
                             .order_by(AdminGrant.permission, AdminGrant.scope_id))).scalars().all()
    out: dict[int, list[dict]] = {uid: [] for uid in user_ids}
    for g in rows:
        out[g.user_id].append({"permission": g.permission,
                               "column_id": g.scope_id if g.scope_type == "column" else None})
    return out


async def _content_counts(db: AsyncSession, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = (await db.execute(select(Content.created_by_id, func.count())
                             .where(Content.created_by_id.in_(user_ids))
                             .group_by(Content.created_by_id))).all()
    return {uid: n for uid, n in rows if uid is not None}


async def _media_counts(db: AsyncSession, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = (await db.execute(select(MediaAsset.uploaded_by_id, func.count())
                             .where(MediaAsset.uploaded_by_id.in_(user_ids))
                             .group_by(MediaAsset.uploaded_by_id))).all()
    return {uid: n for uid, n in rows if uid is not None}


def _item(u: User, grants: dict[int, list[dict]], contents: dict[int, int],
          media: dict[int, int]) -> dict:
    mine = grants.get(u.id, [])
    return {
        "id": u.id, "username": u.username, "nickname": u.nickname, "email": u.email,
        "avatar": u.avatar_url or "", "signature": u.signature or "",
        "role": u.role, "is_super": u.role == ROLE_SUPER, "is_active": u.is_active,
        "note": u.note, "last_login_at": u.last_login_at, "created_at": u.created_at,
        "content_count": contents.get(u.id, 0), "media_count": media.get(u.id, 0),
        "grants": mine,
        "permissions": sorted(PERMISSIONS) if u.role == ROLE_SUPER
        else sorted({g["permission"] for g in mine}),
    }


async def row_dict(db: AsyncSession, user: User) -> dict:
    """单个账号的完整视图（含 grants 与归属计数）。super 的 grants 为空——权限隐式全有。"""
    ids = [user.id]
    return _item(user, await _grant_rows(db, ids), await _content_counts(db, ids),
                 await _media_counts(db, ids))


async def list_admins(db: AsyncSession) -> dict:
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    ids = [u.id for u in users]
    grants = await _grant_rows(db, ids)
    contents = await _content_counts(db, ids)
    media = await _media_counts(db, ids)
    items = [_item(u, grants, contents, media) for u in users]
    return {"total": len(items), "items": items}


def _validate_grants_by_actor(keys: set[tuple[str, str, int | None]], *, is_super_actor: bool,
                              actor_perms: set[str]) -> None:
    """下放出去权限的人只能授出自己已具备的权限点，且永远不能把 admin:manage 转授给别人。
    否则「授权」这件事就不在顶级管理员手里了。"""
    if is_super_actor:
        return
    if any(p == "admin:manage" for p, _s, _id in keys):
        raise AppException(ErrorCode.FORBIDDEN, "「管理员账号管理」权限只能由顶级管理员授予")
    missing = sorted({p for p, _s, _id in keys} - actor_perms)
    if missing:
        raise AppException(ErrorCode.FORBIDDEN, "你不能授出自己没有的权限：" + "、".join(missing))


async def create_admin(db: AsyncSession, *, ctx, username: str, password: str, email: str,
                       nickname: str = "", note: str = "",
                       role: str = ROLE_STAFF, grants: list[dict] | None = None) -> dict:
    actor = ctx.user
    username = (username or "").strip()
    if not username:
        raise AppException(ErrorCode.BAD_REQUEST, "用户名不能为空")
    if role not in (ROLE_SUPER, ROLE_STAFF):
        raise AppException(ErrorCode.BAD_REQUEST, f"未知角色「{role}」")
    if role == ROLE_SUPER and not ctx.is_super:
        raise AppException(ErrorCode.FORBIDDEN, "只有顶级管理员能创建 super 账号")
    check_password_strength(password)
    if (await db.execute(select(User.id).where(User.username == username)
                         .limit(1))).first():
        raise AppException(ErrorCode.CONFLICT, f"用户名「{username}」已存在")
    email = await _ensure_email_free(db, email)
    keys = normalize_grants(grants or [])
    _validate_grants_by_actor(keys, is_super_actor=ctx.is_super, actor_perms=set(ctx.permissions))
    user = User(username=username, password_hash=hash_password(password), email=email,
                nickname=nickname or username, note=note, role=role,
                is_active=True, created_by_id=actor.id)
    db.add(user)
    await db.flush()
    for perm, scope_type, scope_id in keys:
        db.add(AdminGrant(user_id=user.id, permission=perm, scope_type=scope_type,
                          scope_id=scope_id, granted_by=actor.id))
    await db.commit()
    return await row_dict(db, user)


async def _replace_grants(db: AsyncSession, *, actor_id: int, target: User,
                          keys: set[tuple[str, str, int | None]]) -> None:
    await db.execute(AdminGrant.__table__.delete().where(AdminGrant.user_id == target.id))
    for perm, scope_type, scope_id in keys:
        db.add(AdminGrant(user_id=target.id, permission=perm, scope_type=scope_type,
                          scope_id=scope_id, granted_by=actor_id))


async def set_grants(db: AsyncSession, *, ctx, admin_id: int, grants: list[dict]) -> dict:
    target = await get_or_404(db, admin_id)
    if target.role == ROLE_SUPER:
        raise AppException(ErrorCode.CONFLICT, "顶级管理员隐式拥有全部权限，无需授权")
    if target.id == ctx.user.id:
        raise AppException(ErrorCode.FORBIDDEN, "不能修改自己的权限")
    keys = normalize_grants(grants)
    _validate_grants_by_actor(keys, is_super_actor=ctx.is_super, actor_perms=set(ctx.permissions))
    await _replace_grants(db, actor_id=ctx.user.id, target=target, keys=keys)
    await db.commit()
    return await row_dict(db, target)


async def update_admin(db: AsyncSession, *, ctx, admin_id: int, fields: dict) -> dict:
    """覆盖式改昵称/备注/启停/角色。护栏：最后一个可用 super 不可停用或降级（409）；
    不可停用或降级自己（403）；非 super 不能触碰 super 身份（403）。"""
    actor, is_super_actor = ctx.user, ctx.is_super
    target = await get_or_404(db, admin_id)
    profile = {k: v for k, v in fields.items() if k in PROFILE_KEYS}
    if profile and not is_super_actor:
        raise AppException(ErrorCode.FORBIDDEN, "只有顶级管理员能代改他人资料")
    new_role = fields.get("role", target.role)
    new_active = fields.get("is_active", target.is_active)
    if new_role not in (ROLE_SUPER, ROLE_STAFF):
        raise AppException(ErrorCode.BAD_REQUEST, f"未知角色「{new_role}」")
    if not is_super_actor and (target.role == ROLE_SUPER or new_role == ROLE_SUPER):
        raise AppException(ErrorCode.FORBIDDEN, "只有顶级管理员能变更 super 身份")
    loses_super = target.role == ROLE_SUPER and (new_role != ROLE_SUPER or new_active is False)
    if loses_super and await _active_super_count(db) <= 1:
        raise AppException(ErrorCode.CONFLICT, "这是最后一个可用的顶级管理员，不能停用或降级")
    if target.id == actor.id and (new_role != ROLE_SUPER or new_active is False):
        raise AppException(ErrorCode.FORBIDDEN, "不能停用自己或变更自己的顶级身份")
    if "nickname" in fields:
        target.nickname = fields["nickname"] or target.username
    if "note" in fields:
        target.note = fields["note"] or ""
    if "email" in fields:
        target.email = await _ensure_email_free(db, fields["email"], exclude_id=target.id)
    if "role" in fields:
        target.role = fields["role"]
    if "is_active" in fields:
        target.is_active = bool(new_active)
        if not new_active:
            target.token_version += 1      # 停用即全端下线
    if fields.get("password"):
        check_password_strength(fields["password"])
        target.password_hash = hash_password(fields["password"])
        target.token_version += 1
    await db.commit()
    if profile:
        await profile_svc.update_profile(db, target, profile)
    return await row_dict(db, target)


def apply_reset(target: User, password: str) -> None:
    """写入新口令并强制下线。不含 commit —— 忘记密码流程要等邮件发出去才落盘。"""
    target.password_hash = hash_password(password)
    target.token_version += 1              # 旧会话立即失效
    target.failed_attempts = 0
    target.locked_until = None


async def reset_password(db: AsyncSession, *, admin_id: int) -> tuple[dict, str]:
    target = await get_or_404(db, admin_id)
    password = gen_password()
    apply_reset(target, password)
    await db.commit()
    return await row_dict(db, target), password


async def delete_admin(db: AsyncSession, *, actor: User, admin_id: int) -> None:
    """仅允许删除从未上传过内容/素材的账号；有归属数据一律引导停用（409）。"""
    target = await get_or_404(db, admin_id)
    if target.id == actor.id:
        raise AppException(ErrorCode.FORBIDDEN, "不能删除自己")
    if target.role == ROLE_SUPER and await _active_super_count(db) <= 1:
        raise AppException(ErrorCode.CONFLICT, "这是最后一个可用的顶级管理员，不能删除")
    contents = await _content_counts(db, [target.id])
    media = await _media_counts(db, [target.id])
    if contents.get(target.id) or media.get(target.id):
        raise AppException(ErrorCode.CONFLICT,
                           "该账号名下已有内容或素材，请改用停用以保留归属")
    await db.execute(AdminGrant.__table__.delete().where(AdminGrant.user_id == target.id))
    await db.delete(target)
    await db.commit()
