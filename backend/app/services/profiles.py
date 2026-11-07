"""账号维度的个人资料：站点级 profile 已废，资料跟人走（2026-10 定案）。

/public 读路径仍返回同名 profile 对象，只是数据源换成 super 那一行，
所以前端 stores/site.ts、HomeView、AboutView 不需要改字段名。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Content, User

# 每位管理员都能改自己这份；能不能改「别人」由调用方判（/admin/profile 只能改自己，
# 代改他人仅 super 走账号端点），不靠字段白名单区分身份。
EDITABLE_FIELDS = ("nickname", "avatar", "signature", "social_links",
                   "bio_md", "skills", "experience")
# 公开可见的作者信息白名单：只有这两项，email/note/role/username 一律不外发
PUBLIC_AUTHOR_FIELDS = ("nickname", "avatar")


async def super_user(db: AsyncSession) -> User | None:
    return (await db.execute(select(User).where(User.role == "super")
                             .order_by(User.id).limit(1))).scalar_one_or_none()


def _profile_dict(u: User) -> dict:
    return {
        "nickname": u.nickname or u.username,
        "avatar": u.avatar_url or "",
        "signature": u.signature or "",
        "bio_md": u.bio_md or "",
        "social_links": u.social_links or [],
        "skills": u.skills or [],
        "experience": u.experience or [],
    }


async def public_profile(db: AsyncSession) -> dict:
    """首页/关于页读的那份 = super 的资料；库里还没有 super 时回落到默认值，不让前台 500。"""
    u = await super_user(db)
    if not u:
        return {"nickname": "", "avatar": "", "signature": "", "bio_md": "",
                "social_links": [], "skills": [], "experience": []}
    return _profile_dict(u)


async def site_profile(db: AsyncSession) -> dict:
    """/site-config 与 /home 用的精简版（字段与旧 profile 组一致，省体积）。"""
    p = await public_profile(db)
    return {k: p[k] for k in ("nickname", "avatar", "signature", "social_links")}


async def team_members(db: AsyncSession) -> list[dict]:
    """「管理团队」名单：所有启用的非 super 管理员，按 id 升序。

    每人一份完整资料（与主体同布局的卡片），但身份类字段（email/username/role/note）
    一律不外发。super 不进名单——它就是 About 的主体，同页出现两遍很怪。停用即下架。
    """
    rows = (await db.execute(
        select(User)
        .where(User.is_active.is_(True), User.role != "super")
        .order_by(User.id))).scalars().all()
    return [_profile_dict(u) for u in rows]


async def home_team(db: AsyncSession) -> list[dict]:
    """首页团队条：所有在职管理员，super 排最前，只发昵称/头像/签名三项。

    与 team_members 的区别是刻意的：About 里 super 是主体、不该再进名单，
    而首页要的是「所有管理员」，所以这里含 super，且不带 bio/skills/experience（首页不放长文）。
    """
    rows = (await db.execute(select(User).where(User.is_active.is_(True))
                             .order_by(User.id))).scalars().all()
    rows = sorted(rows, key=lambda u: (u.role != "super", u.id))
    return [{k: p[k] for k in ("nickname", "avatar", "signature")}
            for p in (_profile_dict(u) for u in rows)]


async def about_payload(db: AsyncSession) -> dict:
    return {**(await public_profile(db)), "team": await team_members(db)}


# About 是预渲染页：这些字段变了要重建，否则线上仍是旧名单/旧资料
ABOUT_FIELDS = frozenset({"nickname", "avatar", "signature", "social_links",
                          "bio_md", "skills", "experience"})
ABOUT_TRIGGER_FIELDS = ABOUT_FIELDS | {"is_active"}


def about_visible(u: User) -> bool:
    """这一行是否上 About：主体账号与所有在职管理员都上，只有停用才下架。"""
    return u.is_active


async def author_of(db: AsyncSession, c: Content) -> dict:
    """内容页署名：作者本人优先；无主或已停用则回落 super，前台不出现空作者。"""
    u = c.created_by
    if u is None or not u.is_active:
        u = await super_user(db)
    if u is None:
        return {"nickname": "", "avatar": ""}
    return {"nickname": u.nickname or u.username, "avatar": u.avatar_url or ""}


def self_view(u: User) -> dict:
    """后台「我的资料」：含只有管理员自己看得到的项。"""
    return {"id": u.id, "username": u.username, "email": u.email, **_profile_dict(u)}


def is_super(u: User) -> bool:
    return u.role == "super"


async def update_profile(db: AsyncSession, user: User, fields: dict) -> dict:
    """按白名单落库。`avatar` 是 API 名，落到 avatar_url 列。"""
    allowed = set(EDITABLE_FIELDS)
    for key in fields:
        if key not in allowed:
            raise ValueError(f"不能修改「{key}」")
    for key, value in fields.items():
        if key in ("social_links", "skills", "experience") and not isinstance(value, list):
            raise ValueError(f"「{key}」需为列表")
        if key == "avatar":
            user.avatar_url = (value or "").strip() or None
        elif key == "nickname":
            user.nickname = (value or "").strip() or user.username
        else:
            setattr(user, key, value)
    await db.commit()
    return self_view(user)
