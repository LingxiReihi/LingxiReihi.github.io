import os
from pathlib import Path

TEST_DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret"
os.environ["MEDIA_ROOT"] = str(Path(__file__).parent / "test_media")
os.environ["SITE_URL"] = "https://example.com"
os.environ["REBUILD_SCRIPT"] = ""       # 流水线走 skipped 分支
os.environ["REBUILD_MERGE_SECONDS"] = "0"  # 测试内即时 flush
os.environ["BAIDU_PUSH_API"] = ""       # pending_push 分支
os.environ["SEO_PUSH_ENABLED"] = "false"
# 邮件通道：即使开发者本地 .env 填了真 key，测试也绝不真发信（单测一律用 MockTransport）
os.environ["MAIL_API_URL"] = ""
os.environ["MAIL_API_KEY"] = ""
os.environ["MAIL_OVERRIDE_TO"] = ""

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401  (register tables)
from app.main import app as fastapi_app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    # 每测试重建全部表（避免 Windows 文件句柄问题，不做 unlink）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth(admin_user, client):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    token = r.json()["data"]["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest_asyncio.fixture
async def admin_user():
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import User
    from app.services.auth import ensure_admin
    async with SessionLocal() as db:
        user = await ensure_admin(db, "admin", "test-pass-123", nickname="Test")
        if user is None:
            user = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
        return user


STAFF_PASSWORD = "staff-pass-123"


@pytest_asyncio.fixture
async def make_staff(auth):
    """以顶级管理员身份建一个 staff 账号，返回响应 data（含 id/username）。"""
    async def _make(username: str, *, password: str = STAFF_PASSWORD, email: str | None = None,
                    nickname: str | None = None, grants: list[dict] | None = None):
        r = await auth.post("/api/v1/admin/admins", json={
            "username": username, "password": password,
            "nickname": nickname or username, "email": email or f"{username}@example.test",
            "grants": grants or []})
        assert r.status_code == 200, r.text
        return r.json()["data"]
    return _make
