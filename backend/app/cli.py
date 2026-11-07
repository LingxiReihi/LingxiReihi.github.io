"""CLI: python -m app.cli seed|mail-drain|mail-status
幂等创建管理员 + 默认 settings。管理员凭据来自 env ADMIN_USERNAME/ADMIN_PASSWORD（缺省 admin / 随机生成并打印一次）。
mail-drain 是发信队列的兜底冲刷（入队时已顺带冲一次，没有新事件时靠它），mail-status 打印积压与最近错误。
"""
import asyncio
import os
import secrets
import sys

from dotenv import dotenv_values

from .core.db import SessionLocal
from .models import SiteSetting
from .services.auth import ensure_admin

# .env 仅用于本地开发便利（uvicorn[standard] 自带 python-dotenv）
os.environ.setdefault("ADMIN_USERNAME", dotenv_values(".env").get("ADMIN_USERNAME", "admin"))
if not os.environ.get("ADMIN_PASSWORD"):
    os.environ["ADMIN_PASSWORD"] = dotenv_values(".env").get("ADMIN_PASSWORD", "") or secrets.token_urlsafe(12)

DEFAULT_SETTINGS: dict = {
    "site.title": "My Blog",
    "site.subtitle": "",
    "site.description": "",
    # profile.* 已删：个人资料改存在管理员账号行上（services/profiles.py）
    # home.sections 与 home.featured_content_ids 已删：首页改版成 最新/热门/团队 三段（迁移 b7f3d2c8a5e4 清旧行）
    "nav.items": [
        {"label": "首页", "path": "/", "visible": True, "order": 1},
        {"label": "博客", "path": "/blog", "visible": True, "order": 2},
        {"label": "模型", "path": "/models", "visible": True, "order": 3},
        {"label": "杂谈", "path": "/chats", "visible": True, "order": 4},
        {"label": "关于", "path": "/about", "visible": True, "order": 5},
    ],
    "footer.links": [],
    "footer.copyright": "",
}


async def seed() -> None:
    async with SessionLocal() as db:
        from sqlalchemy import select
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        # 资料跟人走：昵称落在 super 那一行（About 页读它），不再是 site_settings.profile
        created = await ensure_admin(db, username, password,
                                     nickname=os.environ.get("ADMIN_NICKNAME", "博主"))
        if created:
            print(f"[seed] admin created: username={username} password={password}")
        else:
            print(f"[seed] admin already exists: {username} (skip)")
        for key, value in DEFAULT_SETTINGS.items():
            if (await db.execute(select(SiteSetting).where(SiteSetting.key == key))).scalar_one_or_none() is None:
                db.add(SiteSetting(key=key, value=value))
        await db.commit()
        print("[seed] default settings ensured")


async def mail_drain() -> None:
    """把到点的待发信冲出去。入队时会顺带冲刷一次，这条命令是「没有新事件时也能补发」的兜底，
    由服务器 cron 每小时调一次（docs/deployment.md §3-C 邮件通道）。"""
    from .services import mail_queue
    stats = await mail_queue.drain_now()
    print("[mail] drain " + " ".join(f"{k}={v}" for k, v in stats.items()))


async def mail_status() -> None:
    import json

    from .services import mail_queue
    async with SessionLocal() as db:
        print(json.dumps(await mail_queue.summary(db), ensure_ascii=False))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd == "seed":
        asyncio.run(seed())
    elif cmd == "mail-drain":
        asyncio.run(mail_drain())
    elif cmd == "mail-status":
        asyncio.run(mail_status())
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)
