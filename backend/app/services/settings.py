"""site_settings 分组读写（key 形如 'group.field'）。"""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import decrypt_secret, encrypt_secret
from ..models import SiteSetting
from . import profiles


async def get_group(db: AsyncSession, group: str) -> dict:
    rows = (await db.execute(
        select(SiteSetting).where(SiteSetting.key.like(f"{group}.%")))).scalars().all()
    out = {}
    for r in rows:
        out[r.key.split(".", 1)[1]] = r.value
    return out


MAIL_GROUP = "mail"
MAIL_SECRET_FIELD = "api_key"
# api_key 只写不读：库里存密文，读接口换成下面两个派生键，前端原样 PUT 回来也不会污染存储
MAIL_DERIVED_FIELDS = ("api_key_set", "api_key_hint")


def redact_group(group: str, values: dict) -> dict:
    if group != MAIL_GROUP:
        return values
    key = decrypt_secret(values.get(MAIL_SECRET_FIELD))   # 尾号从解出的明文算，明文本身不进响应
    out = {k: v for k, v in values.items() if k != MAIL_SECRET_FIELD}
    out["api_key_set"] = bool(key)
    out["api_key_hint"] = key[-4:]
    return out


async def set_group(db: AsyncSession, group: str, body: dict) -> dict:
    """整组覆盖写入（调用方负责失效缓存）。"""
    if group == MAIL_GROUP:
        body = {k: v for k, v in body.items() if k not in MAIL_DERIVED_FIELDS}
        plain = str(body.get(MAIL_SECRET_FIELD) or "").strip()
        if plain:
            body[MAIL_SECRET_FIELD] = encrypt_secret(plain)
        else:
            # 界面回显的是掩码，留空只能解释为「不改」，否则一次保存就把凭据洗没了
            body[MAIL_SECRET_FIELD] = (await get_group(db, group)).get(MAIL_SECRET_FIELD) or ""
    await db.execute(delete(SiteSetting).where(SiteSetting.key.like(f"{group}.%")))
    for k, v in body.items():
        db.add(SiteSetting(key=f"{group}.{k}", value=v))
    await db.commit()
    return redact_group(group, await get_group(db, group))


async def get_public_config(db: AsyncSession) -> dict:
    site = await get_group(db, "site")
    nav = await get_group(db, "nav")
    footer = await get_group(db, "footer")
    return {
        "site": {"title": site.get("title", ""), "subtitle": site.get("subtitle", ""),
                 "description": site.get("description", ""), "favicon": site.get("favicon", ""),
                 "icon": site.get("icon", "")},
        "nav_items": sorted(nav.get("items", []), key=lambda i: i.get("order", 99)),
        "footer": {"links": footer.get("links", []), "copyright": footer.get("copyright", ""),
                   "beian": footer.get("beian", "")},
        # profile 组已废（资料跟人走）：字段名不变，数据源换成 super 账号那一行
        "profile": await profiles.site_profile(db),
    }
