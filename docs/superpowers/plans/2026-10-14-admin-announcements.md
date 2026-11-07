# 更新公告（后台仪表盘内嵌管理卡）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后台新增「更新公告」CRUD（新表 + /admin/announcements API），以管理卡形态内嵌进仪表盘页（DashboardView），权限点 `announcement:manage`。

**Architecture:** 独立 `announcements` 表（status 预留前台，本期无公开端点、不接重建链路）；后端服务层唯一排序实现 + 四端点全挂权限判定；前端不建新路由，卡片进 `DashboardView.vue` 顶部，弹窗照 TagsView 样板，正文经 `renderMd()` 渲进 `.prose`（vue 主题）。

**Tech Stack:** FastAPI + SQLAlchemy(async) + aiosqlite + alembic；Vue3 + Naive UI + Tailwind；pytest-asyncio + httpx ASGITransport。

**Spec:** `docs/superpowers/specs/2026-10-14-admin-announcements-design.md`（本计划逐节实现它，冲突以 spec 为准）

## Global Constraints

- 统一响应包：成功 `errors.ok(data)` → `{code:0,message,data}`；业务错 `AppException(ErrorCode.X, "中文")`；`ErrorCode.NOT_FOUND=40400→404`、`BAD_REQUEST=40000→400`、`FORBIDDEN=40300→403`；Pydantic 校验失败由全局 handler 转 422。
- 时间一律 `app.core.db` 的 `TZDateTime` + `utcnow`（UTC aware）；出参 `.isoformat()`。
- 权限点只加进 `backend/app/core/permissions.py` 的 `PERMISSIONS`，**不进** `SCOPED_PERMISSIONS`（带 column_id 的授权会被 `admin_accounts.py` 现有校验拒）。
- 公开出参不含 created_by_id 原值，只出 `created_by` 昵称（资料跟人走口径：nickname only，绝不外泄 email/username）。
- 前端 `api<T>()` 包装已解掉响应包，返回值即 `data`。
- 提交信息中文 conventional commit；每个 Task 提交前必须有本轮测试/检查回执。
- 本地后端一律 `backend/.venv/Scripts/...`；8000 端口先查残留实例再起。
- 上线走 personal-web-deploy-verify-loop 七步；本轮**有新迁移 → 上线前备份库**，且 `compose build backend` 必做；手动重建避开 0/4/8/12/16/20 整点。

---

### Task 1: 数据层 —— Announcement 模型 + alembic 迁移

**Files:**
- Create: `backend/app/models/announcement.py`
- Modify: `backend/app/models/__init__.py`（import + `__all__` 两处）
- Create: `backend/alembic/versions/c9e2f4a7b108_add_announcements.py`
- Test: `backend/tests/test_announcements.py`（本 Task 只建文件 + schema 用例）

**Interfaces:**
- Produces: ORM `Announcement(id, title, body_md, status, published_at, created_at, updated_at, created_by_id)`，`__tablename__="announcements"`；迁移链头 `b7f3d2c8a5e4 → c9e2f4a7b108`。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_announcements.py`：

```python
"""更新公告：表结构 / API 契约 / 权限 / 排序。"""
import pytest

from app.core.db import SessionLocal


@pytest.mark.asyncio
async def test_table_created_from_metadata():
    from sqlalchemy import inspect

    from app.models import Announcement  # noqa: F401  (Task 1 先建模型)
    from app.core.db import engine
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda s: inspect(s).get_columns("announcements"))}
    assert cols == {"id", "title", "body_md", "status", "published_at",
                    "created_at", "updated_at", "created_by_id"}
```

（文件顶部 `SessionLocal` 本 Task 未用到会报 lint 未用——如仓库 ruff/flake8 门禁报未用 import，删该行，Task 2 用到时再加回。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py -x -q`
Expected: FAIL —— `ImportError: cannot import name 'Announcement'`（或表不存在）。

- [ ] **Step 3: 写模型**

`backend/app/models/announcement.py`：

```python
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, TZDateTime, utcnow


class Announcement(Base):
    """更新公告：本期仅后台仪表盘消费；status/published_at 为前台预留。"""
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="published")   # draft | published
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True)

    created_by: Mapped["User | None"] = relationship(lazy="selectin")  # noqa: F821
```

`backend/app/models/__init__.py`：在 `from .setting import SiteSetting` 下方加 `from .announcement import Announcement`，`__all__` 列表加 `"Announcement",`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py -x -q`
Expected: PASS（conftest 的 `_fresh_db` 从 metadata 建表，不依赖迁移）。

- [ ] **Step 5: 写迁移文件**

`backend/alembic/versions/c9e2f4a7b108_add_announcements.py`（命名风格照 `b7f3d2c8a5e4_retire_home_settings.py`）：

```python
"""add announcements: 后台更新公告表（本期仅仪表盘消费）

用户要求「后台添加更新公告功能，并合并到仪表盘页面」。选独立表而非 site_settings 新组：
逐条 id/时间戳/排序可控、量大不失控，status 为以后接前台预留（届时无新迁移）。

Revision ID: c9e2f4a7b108
Revises: b7f3d2c8a5e4
Create Date: 2026-10-14 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e2f4a7b108'
down_revision: Union[str, Sequence[str], None] = 'b7f3d2c8a5e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_announcements_created_by_id", "announcements", ["created_by_id"])
    op.create_index("ix_announcements_status_pub", "announcements", ["status", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_announcements_status_pub", table_name="announcements")
    op.drop_index("ix_announcements_created_by_id", table_name="announcements")
    op.drop_table("announcements")
```

- [ ] **Step 6: 临时库上跑迁移双向验证**

Run（PowerShell 语法在 Git Bash 下用 env 前缀）:

```bash
cd backend && DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig-test.db" .venv/Scripts/python.exe -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig-test.db" .venv/Scripts/python.exe -m alembic downgrade -1
DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig-test.db" .venv/Scripts/python.exe -m alembic upgrade head
rm data/tmp-mig-test.db*
```

Expected: 三条命令均无异常退出（downgrade 能退 = 表可删净）。

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/announcement.py backend/app/models/__init__.py backend/alembic/versions/c9e2f4a7b108_add_announcements.py backend/tests/test_announcements.py
git commit -m "feat(announcements): announcements 表 + 模型 + 迁移 c9e2f4a7b108 — …"
```

---

### Task 2: 后端 API —— 服务层 + 四端点 + 权限点 + 契约测试

**Files:**
- Modify: `backend/app/core/permissions.py`（PERMISSIONS 加一行）
- Modify: `backend/app/schemas/admin.py`（文件末尾追加两个 DTO）
- Create: `backend/app/services/announcements.py`
- Create: `backend/app/api/admin/announcements.py`
- Modify: `backend/app/main.py`（import 区 + include_router 区各一行）
- Test: `backend/tests/test_announcements.py`（追加契约用例）

**Interfaces:**
- Consumes: Task 1 的 `Announcement` 模型。
- Produces: `GET/POST /api/v1/admin/announcements`、`PUT/DELETE /api/v1/admin/announcements/{id}`；出参 dict 形如 `{id,title,body_md,status,published_at,created_at,created_by}`（时间为 isoformat 字符串或 null，created_by 为昵称字符串或 null）；服务函数 `list_announcements(db, limit=20)`、`to_dict(a)`、`apply_write(a, *, title, body_md, status, published_at, user_id)`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_announcements.py` 顶部 import 区补 `from datetime import datetime, timezone`（`SessionLocal` 保留，SET NULL 用例要用），然后追加：

```python
async def _post(auth, **over):
    body = {"title": "v1 上线", "body_md": "## 变更\n- 表格 | a | b |\n|---|---|\n| 1 | 2 |",
            "status": "published", "published_at": "2026-10-14T12:00:00+00:00"}
    body.update(over)
    return await auth.post("/api/v1/admin/announcements", json=body)


async def _staff_client(auth, make_staff, username, grants):
    await make_staff(username, grants=grants)
    from httpx import ASGITransport, AsyncClient
    from app.main import app as fastapi_app
    c = AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test")
    r = await c.post("/api/v1/admin/auth/login",
                     json={"username": username, "password": "staff-pass-123"})
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


@pytest.mark.asyncio
async def test_crud_flow(auth):
    r = await _post(auth)
    assert r.status_code == 200 and r.json()["code"] == 0
    a = r.json()["data"]
    assert a["status"] == "published" and a["created_by"] == "Test"
    got = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert got[0]["id"] == a["id"]
    r2 = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"title": "v1 修订"})
    assert r2.status_code == 200 and r2.json()["data"]["title"] == "v1 修订"
    assert r2.json()["data"]["body_md"] == a["body_md"]          # 部分更新不动其它字段
    assert (await auth.delete(f"/api/v1/admin/announcements/{a['id']}")).status_code == 200
    assert (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_staff_without_perm_gets_403_on_read_and_write(auth, make_staff):
    c = await _staff_client(auth, make_staff, "s_noperm", [])
    r = await c.get("/api/v1/admin/announcements")
    assert r.status_code == 403 and r.json()["code"] == 40300
    assert "更新公告" in r.json()["message"]
    assert (await c.post("/api/v1/admin/announcements", json={"title": "x"})).status_code == 403
    await c.aclose()


@pytest.mark.asyncio
async def test_staff_with_announcement_perm(auth, make_staff):
    c = await _staff_client(auth, make_staff, "s_ann",
                            [{"permission": "announcement:manage"}])
    assert (await c.get("/api/v1/admin/announcements")).status_code == 200
    assert (await _post(c, title="授权可写")).status_code == 200
    await c.aclose()


@pytest.mark.asyncio
async def test_title_blank_rejected(auth):
    assert (await _post(auth, title="")).status_code == 400
    assert (await _post(auth, title="   ")).status_code == 400


@pytest.mark.asyncio
async def test_unknown_status_422(auth):
    assert (await _post(auth, status="archived")).status_code == 422


@pytest.mark.asyncio
async def test_ordering_published_desc_then_draft(auth):
    await _post(auth, title="早", published_at="2026-09-01T00:00:00+00:00")
    await _post(auth, title="晚", published_at="2026-10-01T00:00:00+00:00")
    await _post(auth, title="草稿", status="draft", published_at=None)
    items = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert [i["title"] for i in items] == ["晚", "早", "草稿"]


@pytest.mark.asyncio
async def test_draft_without_date_and_republish_keeps_first_date(auth):
    a = (await _post(auth, status="draft", published_at=None)).json()["data"]
    assert a["published_at"] is None and a["status"] == "draft"
    r = await auth.put(f"/api/v1/admin/announcements/{a['id']}",
                       json={"status": "published", "published_at": None})
    assert r.json()["data"]["published_at"] is not None          # 置发布且没给日期 → 补 now
    first = r.json()["data"]["published_at"]
    r2 = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"status": "draft"})
    assert r2.json()["data"]["published_at"] == first             # 改回草稿不清空
    r3 = await auth.put(f"/api/v1/admin/announcements/{a['id']}", json={"status": "published"})
    assert r3.json()["data"]["published_at"] == first             # 重发布不覆盖首发时间


@pytest.mark.asyncio
async def test_created_by_set_null_on_user_delete(auth):
    a = (await _post(auth)).json()["data"]
    async with SessionLocal() as db:
        from sqlalchemy import delete

        from app.models import User
        await db.execute(delete(User).where(User.username == "admin"))
        await db.commit()
    items = (await auth.get("/api/v1/admin/announcements")).json()["data"]["items"]
    assert items[0]["id"] == a["id"] and items[0]["created_by"] is None


@pytest.mark.asyncio
async def test_put_missing_id_404(auth):
    assert (await auth.put("/api/v1/admin/announcements/99999", json={"title": "x"})).status_code == 404
    assert (await auth.delete("/api/v1/admin/announcements/99999")).status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py -q`
Expected: 新用例全 FAIL/ERROR（404 路由不存在 / 权限点未知），`test_table_created_from_metadata` 仍 PASS。

- [ ] **Step 3: 权限点 + DTO**

`backend/app/core/permissions.py` 的 `PERMISSIONS` 集合内 `"log:view",` 之后加：

```python
    "announcement:manage",  # 更新公告（仪表盘公告卡，仅全局）
```

`backend/app/schemas/admin.py` 文件末尾追加：

```python
class AnnouncementReq(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body_md: str = ""
    status: Literal["draft", "published"] = "published"
    published_at: datetime | None = None


class AnnouncementPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    body_md: str | None = None
    status: Literal["draft", "published"] | None = None
    published_at: datetime | None = None
```

并把该文件首行 import 改为 `from datetime import datetime`（现无此 import，加在 `from typing import Literal` 旁）。

- [ ] **Step 4: 服务层**

`backend/app/services/announcements.py`：

```python
"""更新公告读写。排序口径唯一实现处：published 按发布时间倒序，draft 垫底、组内创建时间倒序。
（SQLite 不支持 NULLS LAST，用 (published_at IS NULL) 双键等价。）"""
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import utcnow
from ..models import Announcement

STATUSES = ("draft", "published")


def to_dict(a: Announcement) -> dict:
    return {
        "id": a.id, "title": a.title, "body_md": a.body_md, "status": a.status,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "created_by": a.created_by.nickname if a.created_by else None,
    }


async def list_announcements(db: AsyncSession, limit: int = 20) -> list[Announcement]:
    limit = max(1, min(limit, 100))
    null_last = case((Announcement.published_at.is_(None), 1), else_=0)
    rows = (await db.execute(
        select(Announcement)
        .order_by(null_last, Announcement.published_at.desc(), Announcement.created_at.desc())
        .limit(limit))).scalars().all()
    return list(rows)


def apply_write(a: Announcement, *, title: str | None = None, body_md: str | None = None,
                status: str | None = None, published_at=None, user_id: int | None = None) -> None:
    """新建与部分更新共用：title/body 传 None 即不动；发布语义见三条注释。"""
    if title is not None:
        a.title = title.strip()
    if body_md is not None:
        a.body_md = body_md
    if published_at is not None:
        a.published_at = published_at
    if status is not None and status != a.status:
        # 置 published 且从无发布时间（或草稿期改过日期又清空）→ 补 now；已有首发时间不动（重发布不覆盖）；
        # 改回 draft 保留 published_at（spec §2）。
        if status == "published" and a.published_at is None:
            a.published_at = utcnow()
        a.status = status
    if user_id is not None and a.created_by_id is None:
        a.created_by_id = user_id
```

注意一个边界：`test_draft_without_date_and_republish_keeps_first_date` 里 PUT `{"status":"published","published_at":None}` —— Pydantic `exclude_unset` 下 published_at 不在 diff 里，不会进 `published_at` 分支，正确。但 POST 草稿带 `published_at=None` 是显式构造，`Announcement(published_at=None)` 落 NULL，也正确。

- [ ] **Step 5: 路由**

`backend/app/api/admin/announcements.py`：

```python
"""更新公告 CRUD（仪表盘公告卡数据源）。读写都要 announcement:manage——公告是管理侧内容，
无权限者前端整卡隐藏，不存在只读游客。不接 trigger_rebuild/sitemap：前台无消费者。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import get_db
from ...core.deps import AdminContext, get_admin_ctx
from ...core.errors import AppException, ErrorCode, ok
from ...models import Announcement
from ...schemas.admin import AnnouncementPatch, AnnouncementReq
from ...services import announcements as svc

router = APIRouter(prefix="/announcements", tags=["admin-announcements"])


async def _get(db: AsyncSession, announcement_id: int) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if not a:
        raise AppException(ErrorCode.NOT_FOUND, "公告不存在")
    return a


@router.get("")
async def list_announcements(limit: int = 20, db: AsyncSession = Depends(get_db),
                             ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    rows = await svc.list_announcements(db, limit)
    return ok({"items": [svc.to_dict(a) for a in rows]})


@router.post("")
async def create_announcement(body: AnnouncementReq, db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    a = Announcement(title=body.title.strip(), body_md=body.body_md, status=body.status,
                     published_at=body.published_at, created_by_id=ctx.user.id)
    if a.status == "published" and a.published_at is None:
        from ...core.db import utcnow
        a.published_at = utcnow()
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return ok(svc.to_dict(a))


@router.put("/{announcement_id}")
async def update_announcement(announcement_id: int, body: AnnouncementPatch,
                              db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    a = await _get(db, announcement_id)
    svc.apply_write(a, **body.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(a)
    return ok(svc.to_dict(a))


@router.delete("/{announcement_id}")
async def delete_announcement(announcement_id: int, db: AsyncSession = Depends(get_db),
                              ctx: AdminContext = Depends(get_admin_ctx)):
    ctx.need("announcement:manage", subject="更新公告")
    a = await _get(db, announcement_id)
    await db.delete(a)
    await db.commit()
    return ok({"deleted": announcement_id})
```

title 空白 400：Pydantic `min_length=1` 只挡空串，`"   "` 要在路由前拒绝——在 `AnnouncementReq`/`AnnouncementPatch` 各加一个校验器（两 DTO 同构，都写）：

```python
    @field_validator("title")
    @classmethod
    def _strip_title(cls, v):
        if v is not None and not v.strip():
            raise ValueError("标题不能为空")
        return v.strip() if isinstance(v, str) else v
```

（`field_validator` 该文件已 import；ValueError 由全局 handler 转 400 或 422 —— 实现时以 `test_title_blank_rejected` 断言为准：若全局把 validator 错误转 422，则把该测试两行断言改为 `== 422` 并在 commit message 注明口径；空串 `""` 走 min_length 恒 422，所以**测试预期统一按实测改**，不迁就计划。）

`backend/app/main.py`：import 区加 `from .api.admin import announcements as announcements_api`（照现有 `site_api` 那组 import 的写法），include 区 `logs_api` 之前加：

```python
    app.include_router(announcements_api.router, prefix=f"{api}/admin")
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py -q`
Expected: 全 PASS（含 Task 1 的 schema 用例）。再跑全量回归：`... -m pytest tests -q`，Expected: 全绿、无既有用例被 PERMISSIONS 加项打挂（`AdminContext.permissions` 对 super 返回全量白名单——若某测试钉死了 super 权限列表长度/内容，按新点更新该测试，这是预期变更）。

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/permissions.py backend/app/schemas/admin.py backend/app/services/announcements.py backend/app/api/admin/announcements.py backend/app/main.py backend/tests/test_announcements.py
git commit -m "feat(announcements): /admin/announcements 四端点 + announcement:manage 权限点 + 契约测试 10 例 — …"
```

---

### Task 3: 前端 —— API 客户端 + 类型 + AdminsView 权限文案

**Files:**
- Modify: `frontend/src/api/types.ts`（追加接口）
- Modify: `frontend/src/api/index.ts`（`adminTagsApi` 之后追加）
- Modify: `frontend/src/views/admin/AdminsView.vue:25`（PERMS 数组 `setting:manage` 行后插一行）

**Interfaces:**
- Consumes: Task 2 的出参形状（`{id,title,body_md,status,published_at,created_at,created_by}`）。
- Produces: `adminAnnouncementsApi.{list,create,update,remove}`、`Announcement` 类型，Task 4 消费。

- [ ] **Step 1: 类型**

`frontend/src/api/types.ts` 末尾追加：

```ts
/** 更新公告（本期仅后台仪表盘消费；status 为前台预留） */
export interface Announcement {
  id: number
  title: string
  body_md: string
  status: 'draft' | 'published'
  published_at: string | null
  created_at: string | null
  created_by: string | null
}
```

- [ ] **Step 2: 客户端**

`frontend/src/api/index.ts`：type import 列表加 `Announcement,`（保持字母序在 `AboutData` 后），`adminTagsApi` 对象之后加：

```ts
export const adminAnnouncementsApi = {
  list: (limit?: number) => api<{ items: Announcement[] }>({ url: '/admin/announcements', params: q({ limit }) }),
  create: (body: { title: string; body_md?: string; status?: 'draft' | 'published'; published_at?: string | null }) =>
    api<Announcement>({ url: '/admin/announcements', method: 'post', data: body }),
  update: (id: number, body: Partial<{ title: string; body_md: string; status: 'draft' | 'published'; published_at: string | null }>) =>
    api<Announcement>({ url: `/admin/announcements/${id}`, method: 'put', data: body }),
  remove: (id: number) => api<{ deleted: number }>({ url: `/admin/announcements/${id}`, method: 'delete' }),
}
```

- [ ] **Step 3: 授权页文案表**

`AdminsView.vue` 的 `PERMS` 数组，`setting:manage` 行后插：

```ts
  { key: 'announcement:manage', label: '更新公告', hint: '仪表盘公告卡的新建/编辑/删除（仅全局）', scoped: false },
```

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npx vue-tsc -b`
Expected: exit 0。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/index.ts frontend/src/views/admin/AdminsView.vue
git commit -m "feat(announcements): 前端 API 客户端/类型 + 授权页权限文案表补 announcement:manage — …"
```

---

### Task 4: 前端 —— DashboardView 内嵌「更新公告」管理卡

**Files:**
- Create: `frontend/src/views/admin/AnnouncementCard.vue`
- Modify: `frontend/src/views/admin/DashboardView.vue`（import + 模板插卡）

**Interfaces:**
- Consumes: Task 3 的 `adminAnnouncementsApi` / `Announcement`；`@/composables/useMd` 的 `renderMd(src): { html, toc }`；`useAuthStore().can('announcement:manage')`。
- Produces: 组件 `AnnouncementCard`（无 props），渲染在仪表盘标题行与 KPI 栅格之间。

- [ ] **Step 1: 写组件**

`frontend/src/views/admin/AnnouncementCard.vue`：

```vue
<script setup lang="ts">
import {
  NButton, NDatePicker, NInput, NModal, NPopconfirm, NTag, useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import { adminAnnouncementsApi } from '@/api'
import type { Announcement } from '@/api/types'
import { renderMd } from '@/composables/useMd'

const message = useMessage()
const items = ref<Announcement[]>([])
const loading = ref(false)

/** 正文只走 Markdown 渲染（TOC 用不上，忽略第二返回值的 html） */
const bodies = computed(() => new Map(items.value.map((i) => [i.id, renderMd(i.body_md).html])))

async function load() {
  loading.value = true
  try {
    items.value = (await adminAnnouncementsApi.list()).items
  } catch (e: any) {
    message.error(e?.message || '公告加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

// —— 新建/编辑弹窗（照 TagsView 样板：自控 show + preset card） ——
type EditTarget = { id: number | null; title: string; body_md: string; date: string | null }
const show = ref(false)
const edit = ref<EditTarget | null>(null)
const mode = ref<'edit' | 'preview'>('edit')
const saving = ref(false)
const previewHtml = computed(() => (edit.value ? renderMd(edit.value.body_md).html : ''))

function openCreate() {
  edit.value = { id: null, title: '', body_md: '', date: today() }
  mode.value = 'edit'
  show.value = true
}
function openEdit(it: Announcement) {
  edit.value = { id: it.id, title: it.title, body_md: it.body_md, date: fmtDate(it.published_at ?? it.created_at) }
  mode.value = 'edit'
  show.value = true
}
const today = () => new Date().toISOString().slice(0, 10)
const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : null)

async function save() {
  const e = edit.value
  if (!e) return
  const title = e.title.trim()
  if (!title) { message.warning('请输入公告标题'); return }
  saving.value = true
  const body = { title, body_md: e.body_md, status: e.date ? ('published' as const) : ('draft' as const), published_at: e.date }
  try {
    if (e.id == null) await adminAnnouncementsApi.create(body)
    else await adminAnnouncementsApi.update(e.id, body)
    message.success('已保存')
    show.value = false
    await load()
  } catch (err: any) {
    message.error(err?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(it: Announcement) {
  try {
    await adminAnnouncementsApi.remove(it.id)
    message.success('已删除')
    await load()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}
</script>

<template>
  <section class="rounded-xl border border-line bg-surface p-4">
    <div class="mb-3 flex items-center gap-3">
      <p class="text-sm font-medium text-ink-2">更新公告</p>
      <span class="text-xs text-ink-3">{{ items.length }} 条</span>
      <n-button class="ml-auto" size="tiny" type="primary" @click="openCreate">＋ 新建</n-button>
    </div>
    <div v-if="loading" class="py-6 text-center text-sm text-ink-3">加载中…</div>
    <p v-else-if="!items.length" class="py-6 text-center text-sm text-ink-3">
      还没有公告 —— 点「新建」记录每次上线变更
    </p>
    <ul v-else class="space-y-3">
      <li v-for="it in items" :key="it.id" class="rounded-lg border border-line p-3">
        <div class="flex flex-wrap items-center gap-2">
          <n-tag size="small" :type="it.status === 'published' ? 'success' : 'default'">
            {{ it.status === 'published' ? '已发布' : '草稿' }}
          </n-tag>
          <span class="font-medium">{{ it.title }}</span>
          <span class="text-xs text-ink-3">{{ fmtDate(it.published_at ?? it.created_at) }}
            <template v-if="it.created_by"> · {{ it.created_by }}</template></span>
          <span class="ml-auto flex gap-1">
            <n-button size="tiny" tertiary @click="openEdit(it)">编辑</n-button>
            <n-popconfirm @positive-click="remove(it)">
              <template #trigger>
                <n-button size="tiny" tertiary type="error">删除</n-button>
              </template>
              删除「{{ it.title }}」？
            </n-popconfirm>
          </span>
        </div>
        <div v-if="it.body_md" class="prose mt-2 max-h-72 overflow-y-auto border-t border-line pt-2 text-sm"
             v-html="bodies.get(it.id)" />
      </li>
    </ul>

    <n-modal :show="show" preset="card" :title="edit?.id == null ? '新建公告' : '编辑公告'"
             style="width: 640px" @update:show="(v: boolean) => show = v">
      <div v-if="edit" class="space-y-3">
        <n-input v-model:value="edit.title" placeholder="标题（一行）" maxlength="200" show-count />
        <div class="flex items-center gap-2">
          <span class="text-xs text-ink-3">发布日期</span>
          <n-date-picker v-model:formatted-value="edit.date" value-format="yyyy-MM-dd"
                         type="date" size="small" clearable style="width: 160px" />
          <span class="text-xs text-ink-3">留空 = 存草稿</span>
          <div class="ml-auto flex gap-1">
            <button v-for="m in (['edit', 'preview'] as const)" :key="m"
                    class="rounded px-2 py-1 text-xs"
                    :class="mode === m ? 'bg-elevated text-brand' : 'text-ink-3 hover:text-ink'"
                    @click="mode = m">{{ m === 'edit' ? '编辑' : '预览' }}</button>
          </div>
        </div>
        <n-input v-if="mode === 'edit'" v-model:value="edit.body_md" type="textarea" :rows="10"
                 placeholder="正文（Markdown，支持表格/代码块/标题）" />
        <div v-else class="prose max-h-[40vh] min-h-[180px] overflow-y-auto rounded-lg border border-line p-3"
             v-html="previewHtml" />
        <div class="flex justify-end gap-2">
          <n-button size="small" tertiary @click="show = false">取消</n-button>
          <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
        </div>
      </div>
    </n-modal>
  </section>
</template>
```

实现注意（写码时必须核对，两处历史上踩过）：
1. `today`/`fmtDate` 在 `openCreate`/`openEdit` 之后声明——const 箭头函数不提升，**把这两个 const 挪到首次使用之前**（放到 `// —— 弹窗 ——` 注释块紧上方）。
2. `.prose` 的 vue 主题变量作用域在 `.prose` 自身（2026-10-14 已上线），卡内直接可用，无需额外引样式；暗色下代码卡/表格自动换肤。

- [ ] **Step 2: 挂进仪表盘**

`DashboardView.vue`：script 顶部 import 区加 `import AnnouncementCard from './AnnouncementCard.vue'`（放 `@/api` 组之后按现有排序习惯）；模板标题行 `</div>`（`:164` 那个 mb-5 flex 块）之后、KPI 栅格 `<div class="grid grid-cols-2 …">` 之前插：

```html
    <AnnouncementCard v-if="auth.can('announcement:manage')" class="mb-5" />
```

并在 script 里 `const auth = useAuthStore()`（现在文件里只在 `loadAll` 内临时取用，模板要用需提成模块级；`useAuthStore` 已 import）。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc -b`
Expected: exit 0。

- [ ] **Step 4: 本地浏览器实测（退出门）**

起服务：后端 `cd backend && .venv/Scripts/uvicorn.exe app.main:app --host 127.0.0.1 --port 8000`（先查 8000 残留）；前端 `cd frontend && npm run dev`。应用内浏览器（browser-use）：

1. 登录 `/admin`（用户会话已登录则直接用），进仪表盘 —— 「更新公告」卡出现在标题行下方。
2. 新建：标题「测试公告」+ 正文含表格与代码块的 Markdown → 切「预览」核对渲染 → 保存。
3. 列表出现该条，正文经 `.prose` 渲染（表头实心、表体浅灰半透明 = 本轮 vue 主题口径）。
4. 日期清空再保存 → 徽章变「草稿」、排序垫底；改回有日期 → 回已发布区。
5. 编辑改标题 → 生效；删除 → NPopconfirm 确认后列表空态文案出现。
6. 明暗两态各截一张图（点顶栏切换按钮，`documentElement.classList` 含 `light` 即亮态）。
7. `list_console_messages` 零新增报错。

Expected: 七项全过；任何一项打回修组件再复跑。测试数据留在本地库（用户验收后可手删，**不碰线上**）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/admin/AnnouncementCard.vue frontend/src/views/admin/DashboardView.vue
git commit -m "feat(announcements): 仪表盘内嵌更新公告管理卡 — …"
```

---

### Task 5: 文档同步 + 全量回归 + 收尾

**Files:**
- Modify: `docs/backend-architecture.md`（§4.1 表定义、§5.1 权限点）
- Modify: `docs/frontend-design.md`（Flow H 追加 H4）
- Modify: `docs/api-reference.md`（新增 6.x 小节 + §9 映射速查补行）

**Interfaces:**
- Consumes: Task 1-4 的实际落地形状（以代码为准写文档）。
- Produces: 无代码接口。

- [ ] **Step 1: 三份文档**

- `backend-architecture.md` §4.1 表格加 `announcements` 行（列清单 + 一句「status/published_at 为前台预留，本期无公开端点」）；§5.1 权限点列表补 `announcement:manage`（注明仅全局、读写同权限）。
- `frontend-design.md` Flow H 段末追加 `### H4 更新公告卡`：位置（标题行与 KPI 之间）、闸门（无 announcement:manage 整卡不渲染不发请求）、弹窗字段与「留空=草稿」语义、正文 renderMd+.prose 渲染、不接重建链路的原因。
- `api-reference.md` 在「后台 — 站点设置」小节后新开 `## 6.x 后台 — 更新公告`：四端点方法/路径/请求体/出参字段表 + 403 文案；§9 速查表补「仪表盘公告卡 → /admin/announcements」。

- [ ] **Step 2: 全量回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests -q` → 全绿（记录用例数基线，本轮应为 219+新增）。
Run: `cd frontend && npx vue-tsc -b` → exit 0。

- [ ] **Step 3: Commit**

```bash
git add docs/backend-architecture.md docs/frontend-design.md docs/api-reference.md
git commit -m "docs(announcements): 三份文档同步表定义/权限点/Flow H4/接口参考 — …"
```

---

### Task 6: 上线闭环（personal-web-deploy-verify-loop 七步）

**Files:** 无新改动，执行运维流程。

- [ ] Step 1: `cd frontend && npx vue-tsc -b`（忽略 vite.config.ts 既有 4 报——若已修则应 0 报）。
- [ ] Step 2: 本地实测已在 Task 4 完成；复跑一遍仪表盘冒烟即可。
- [ ] Step 3: `git push`（用户已按惯例自行确认 push 时机——**push 前请示**）。
- [ ] Step 4: `ssh admin@47.82.123.169 'cd /home/admin/personal-web && git status --porcelain=v1 -b && git pull --ff-only'`（工作树已知 4 项遗留未入库文件属正常）。
- [ ] Step 5: 依赖守卫——本轮无 package.json/lock 变更，跳过 npm ci。
- [ ] Step 5b: **新迁移 → 备份库**：`ssh … 'tar czf ~/pw-pre-announcements-$(date +%F-%H%M).tar.gz -C /home/admin/personal-web backend/data .env 前先在容器内 wal_checkpoint + integrity_check'`（照 2026-10-06 邮件队列批次做法：`sudo -n docker compose exec -T backend python -c …`）。
- [ ] Step 6: `cd deploy && sudo -n docker compose build backend && sudo -n docker compose up -d backend`；日志确认 `Running upgrade b7f3d2c8a5e4 -> c9e2f4a7b108`；容器内 `PRAGMA table_info(announcements)` 八列齐全。
- [ ] Step 7: 前端重建（避开 4 小时整点，先 `pgrep -af vite-ssg` 确认无 cron 在跑）→ `rebuild ok: releases/<ts>` → `readlink dist` 等于该 ts。
- [ ] Step 8: 线上验证：未登录 `GET /api/v1/admin/announcements` → 401；登录态由用户自查公告卡；`readlink dist` + 新 DashboardView chunk 内含「更新公告」字样（curl assets grep）。
- [ ] Step 9: 报告 release 号与验证回执。

---

## Self-Review 记录

- Spec §2-§7 各节 → Task 1-6 全覆盖；「不做项」（前台展示/分页/软删/拖拽排序）无泄漏实现。
- 类型一致：`to_dict` 出参字段 = `Announcement` TS 接口 = 测试断言字段；`announcement:manage` 拼写三处（permissions/PERMS 文案/ctx.need）一致。
- 已知不确定点已显式交给执行者：validator 错误的 HTTP 码（400 vs 422）以实测为准改测试，不反向迁就。

---

# v2 追加任务（全员登录弹窗 + 独立管理页）

Spec §9 记录了 v1→v2 的反转理由：v1 把读也钉在 `announcement:manage`，用户换 staff 账号实测
发现「其他管理员看不到公告」。v2 读降为仅登录、形态改弹窗、管理入口独立页、新增已读表。
Task 1-5 的产物全部复用（表、四个管理端点、`.prose` 渲染、弹窗表单、排序与发布语义）。
**Task 6（上线）在 Task 7-10 之后执行。**

## v2 全局约束（叠加在 Global Constraints 之上）

- 读端点（`unread` / `read`）**只 `Depends(get_current_admin)`，不判权限点**；写端点保持 `ctx.need("announcement:manage")`。
- 已读判定唯一实现处在 `services/announcements.py`；`unread` 与 `list_announcements` 共用同一 order_by（提 `_order_keys()`，两处各写迟早漂移）。
- `POST /read` 必须幂等且容忍脏输入（不存在的 id 静默跳过、空数组 200），绝不因脏 id 打断弹窗关闭流程。
- 弹窗是增益不是关卡：拉取失败静默、上报失败只 warning 不重开。
- v1 的 `AnnouncementCard.vue` 与 DashboardView 挂载必须**删净**，不留死代码/死 import。
- 一次登录只弹一次（`fetched` 守卫），路由切换与关闭后都不再请求。

---

### Task 7: 数据层 —— announcement_reads 表 + 迁移

**Files:**
- Modify: `backend/app/models/announcement.py`（追加模型 + `__table_args__` 补关系）
- Modify: `backend/app/models/__init__.py`（两处注册）
- Create: `backend/alembic/versions/d3a9c5e7b412_add_announcement_reads.py`
- Test: `backend/tests/test_announcements.py`（追加 schema 例）

**Interfaces:**
- Consumes: Task 1 的 `Announcement`。
- Produces: ORM `AnnouncementRead(announcement_id, user_id, read_at)`，复合 PK，双 FK CASCADE；迁移链头 `c9e2f4a7b108 → d3a9c5e7b412`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_announcements.py` 追加：

```python
@pytest.mark.asyncio
async def test_reads_table_shape():
    from sqlalchemy import inspect

    from app.core.db import engine
    from app.models import AnnouncementRead  # noqa: F401
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda s: inspect(s).get_columns("announcement_reads"))}
        fks = await conn.run_sync(lambda s: {
            (f["constrained_columns"][0], f["options"].get("ondelete"))
            for f in inspect(s).get_foreign_keys("announcement_reads")})
    assert cols == {"announcement_id", "user_id", "read_at"}
    assert fks == {("announcement_id", "CASCADE"), ("user_id", "CASCADE")}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py::test_reads_table_shape -q`
Expected: FAIL —— `ImportError: cannot import name 'AnnouncementRead'`。

- [ ] **Step 3: 写模型**

`backend/app/models/announcement.py` 末尾追加（文件顶部 import 补 `ForeignKeyConstraint`）：

```python
class AnnouncementRead(Base):
    """逐条已读水位（v2 登录弹窗用）。复合 PK 天然去重；两侧 CASCADE——
    删公告不留悬空已读行，删用户同理，因此「未读数」永不需要脏数据兜底。"""
    __tablename__ = "announcement_reads"

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
```

`backend/app/models/__init__.py`：`from .announcement import Announcement` 改为
`from .announcement import Announcement, AnnouncementRead`，`__all__` 里 `"Announcement",` 后加 `"AnnouncementRead",`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py::test_reads_table_shape -q`
Expected: PASS。

- [ ] **Step 5: 写迁移**

`backend/alembic/versions/d3a9c5e7b412_add_announcement_reads.py`（头部格式照 `c9e2f4a7b108_add_announcements.py`）：

```python
"""add announcement_reads: 逐条已读水位表（v2 登录弹窗）

v1 把公告读也钉在 announcement:manage 上，用户换 staff 账号实测发现其他管理员看不到。
v2 读全员开放 + 「看过就不再打扰」，需要一个按 (公告, 管理员) 记录的水位表。

Revision ID: d3a9c5e7b412
Revises: c9e2f4a7b108
Create Date: 2026-10-14 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a9c5e7b412'
down_revision: Union[str, Sequence[str], None] = 'c9e2f4a7b108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 列、复合主键、两侧 CASCADE 一次性写进 create_table —— SQLite 不支持建表后
    # 再 create_primary_key，分步写会在 upgrade 阶段直接失败。
    op.create_table(
        "announcement_reads",
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("announcement_id", "user_id"),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_announcement_reads_user", "announcement_reads", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_announcement_reads_user", table_name="announcement_reads")
    op.drop_table("announcement_reads")
```

ORM 侧必须同步声明该索引（否则重演 v1 终审抓到的迁移↔metadata 漂移）：给
`AnnouncementRead` 补 `__table_args__ = (Index("ix_announcement_reads_user", "user_id"),)`
并在文件顶部 import `Index`。

- [ ] **Step 6: 临时库双向验证 + 漂移自检**

```bash
cd backend
DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig2.db" .venv/Scripts/python.exe -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig2.db" .venv/Scripts/python.exe -m alembic check
DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig2.db" .venv/Scripts/python.exe -m alembic downgrade -1
DATABASE_URL="sqlite+aiosqlite:///./data/tmp-mig2.db" .venv/Scripts/python.exe -m alembic upgrade head
rm data/tmp-mig2.db*
```

Expected: `alembic check` 输出里**不含 announcement_reads / announcements 相关行**（其他表的既有
SQLite 反射漂移是已知噪声，忽略）。

- [ ] **Step 7: 全量回归 + Commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests -q` → 全绿（基线 230 + 1）。
```bash
git add backend/app/models/announcement.py backend/app/models/__init__.py backend/alembic/versions/d3a9c5e7b412_add_announcement_reads.py backend/tests/test_announcements.py
git commit -m "feat(announcements): announcement_reads 已读表 + 迁移 d3a9c5e7b412 — …"
```

---

### Task 8: 后端 —— unread / read 端点（仅登录）+ 契约测试

**Files:**
- Modify: `backend/app/services/announcements.py`
- Modify: `backend/app/api/admin/announcements.py`
- Modify: `backend/app/schemas/admin.py`（加 `ReadReq`）
- Test: `backend/tests/test_announcements.py`

**Interfaces:**
- Consumes: Task 7 的 `AnnouncementRead`；既有 `to_dict`、`list_announcements`。
- Produces: `GET /api/v1/admin/announcements/unread`、`POST /api/v1/admin/announcements/read`
  （出参 `{marked: int}`）；服务函数 `list_unread(db, user_id, limit=20)`、`mark_read(db, user_id, ids) -> int`。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_unread_readable_without_manage_perm(auth, make_staff):
    await _post(auth, title="全员可见")
    c = await _staff_client(auth, make_staff, "s_readonly", [])
    r = await c.get("/api/v1/admin/announcements/unread")
    assert r.status_code == 200
    assert [i["title"] for i in r.json()["data"]["items"]] == ["全员可见"]
    # 对照：同一 staff 读管理列表仍 403（写侧权限未松动）
    assert (await c.get("/api/v1/admin/announcements")).status_code == 403
    await c.aclose()


@pytest.mark.asyncio
async def test_mark_read_clears_unread_and_is_per_user(auth, make_staff):
    a = (await _post(auth, title="只弹一次")).json()["data"]
    c = await _staff_client(auth, make_staff, "s_a", [])
    aid = a["id"]
    assert (await c.post("/api/v1/admin/announcements/read", json={"ids": [aid]})).status_code == 200
    assert (await c.get("/api/v1/admin/announcements/unread")).json()["data"]["items"] == []
    # 另一用户不受影响
    c2 = await _staff_client(auth, make_staff, "s_b", [])
    assert [i["id"] for i in (await c2.get("/api/v1/admin/announcements/unread")).json()["data"]["items"]] == [aid]
    # admin 自己也没读过
    assert len((await auth.get("/api/v1/admin/announcements/unread")).json()["data"]["items"]) == 1
    await c.aclose(); await c2.aclose()


@pytest.mark.asyncio
async def test_mark_read_idempotent(auth, make_staff):
    a = (await _post(auth, title="幂等")).json()["data"]
    c = await _staff_client(auth, make_staff, "s_idem", [])
    for _ in range(2):
        r = await c.post("/api/v1/admin/announcements/read", json={"ids": [a["id"]]})
        assert r.status_code == 200
    async with SessionLocal() as db:
        n = (await db.execute(sa_text(
            "select count(*) from announcement_reads where user_id = :u"),
            {"u": (await _uid("s_idem"))})).scalar_one()
    assert int(n) == 1
    await c.aclose()


@pytest.mark.asyncio
async def test_mark_read_tolerates_dirty_ids(auth, make_staff):
    c = await _staff_client(auth, make_staff, "s_dirty", [])
    assert (await c.post("/api/v1/admin/announcements/read", json={"ids": []})).json()["data"]["marked"] == 0
    r = await c.post("/api/v1/admin/announcements/read", json={"ids": [999999]})
    assert r.status_code == 200 and r.json()["data"]["marked"] == 0     # 不存在的 id 静默跳过
    async with SessionLocal() as db:
        total = (await db.execute(sa_text("select count(*) from announcement_reads"))).scalar_one()
    assert int(total) == 0
    await c.aclose()


@pytest.mark.asyncio
async def test_delete_announcement_cascades_reads(auth, make_staff):
    a = (await _post(auth, title="级联")).json()["data"]
    c = await _staff_client(auth, make_staff, "s_casc", [])
    await c.post("/api/v1/admin/announcements/read", json={"ids": [a["id"]]})
    await c.aclose()
    assert (await auth.delete(f"/api/v1/admin/announcements/{a['id']}")).status_code == 200
    async with SessionLocal() as db:
        n = (await db.execute(sa_text(
            "select count(*) from announcement_reads where announcement_id = :i"),
            {"i": a["id"]})).scalar_one()
    assert int(n) == 0
```

测试文件顶部 import 区补 `from sqlalchemy import text as sa_text`，并加一个小助手：

```python
async def _uid(username: str) -> int:
    async with SessionLocal() as db:
        return (await db.execute(sa_text("select id from users where username = :u"),
                                 {"u": username})).scalar_one()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py -q`
Expected: 5 新例 FAIL/ERROR（404 路由不存在），v1 的 12 例仍 PASS。

- [ ] **Step 3: 服务层**

`backend/app/services/announcements.py`：import 区把 `select` 扩成 `from sqlalchemy import case, exists, select`，模型 import 补 `AnnouncementRead`。
先把 `list_announcements` 里的 order_by 键提成共用函数（**排序口径必须只有一处**）：

```python
def _order_keys():
    """published 在前、draft 垫底；组内有 published_at 者按发布时间倒序、无者按创建时间倒序。"""
    published_first = case((Announcement.status == "published", 0), else_=1)
    null_last = case((Announcement.published_at.is_(None), 1), else_=0)
    return [published_first, null_last, Announcement.published_at.desc(), Announcement.created_at.desc()]


def _clamp(limit: int) -> int:
    return max(1, min(limit, 100))
```

`list_announcements` 改为用 `_order_keys()` 与 `_clamp(limit)`（行为不变，仅去重）。追加：

```python
async def list_unread(db: AsyncSession, user_id: int, limit: int = 20) -> list[Announcement]:
    rows = (await db.execute(
        select(Announcement).where(~exists().where(
            AnnouncementRead.announcement_id == Announcement.id,
            AnnouncementRead.user_id == user_id))
        .order_by(*_order_keys()).limit(_clamp(limit)))).scalars().all()
    return list(rows)


async def mark_read(db: AsyncSession, user_id: int, ids: list[int]) -> int:
    """幂等 + 容忍脏输入：只接受真实存在的公告 id，已记过的不重复写。"""
    if not ids:
        return 0
    valid = set((await db.execute(
        select(Announcement.id).where(Announcement.id.in_(ids)))).scalars().all())
    if not valid:
        return 0
    have = set((await db.execute(
        select(AnnouncementRead.announcement_id).where(
            AnnouncementRead.user_id == user_id,
            AnnouncementRead.announcement_id.in_(valid)))).scalars().all())
    new = valid - have
    for aid in sorted(new):
        db.add(AnnouncementRead(announcement_id=aid, user_id=user_id))
    if new:
        await db.commit()
    return len(new)
```

- [ ] **Step 4: DTO 与端点**

`backend/app/schemas/admin.py` 末尾：

```python
class AnnouncementReadReq(BaseModel):
    ids: list[int] = []
```

`backend/app/api/admin/announcements.py`：import 补 `from ...core.deps import get_current_admin`、
`from ...schemas.admin import AnnouncementReadReq`、`from ...models import User`。
**路由顺序**：`/unread` 必须声明在 `/{announcement_id}` 之前（本文件只有 GET ""、POST ""、
PUT/DELETE "/{id}"，故只需把 GET /unread 放在 GET "" 之后、PUT /{id} 之前即可，POST /read 同理）。

```python
@router.get("/unread")
async def unread_announcements(limit: int = 20, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_admin)):
    """登录弹窗用：当前管理员未读的公告。读全员开放，不判 announcement:manage。"""
    rows = await svc.list_unread(db, user.id, limit)
    return ok({"items": [svc.to_dict(a) for a in rows]})


@router.post("/read")
async def mark_announcements_read(body: AnnouncementReadReq, db: AsyncSession = Depends(get_db),
                                  user: User = Depends(get_current_admin)):
    """把这批 id 记为该用户已读。弹窗关闭即整批上报，幂等、脏 id 静默跳过。"""
    marked = await svc.mark_read(db, user.id, body.ids)
    return ok({"marked": marked})
```

- [ ] **Step 5: 跑测试确认通过 + 全量**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_announcements.py -q` → 17 passed。
Run: `cd backend && .venv/Scripts/python.exe -m pytest tests -q` → 全绿。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/announcements.py backend/app/api/admin/announcements.py backend/app/schemas/admin.py backend/tests/test_announcements.py
git commit -m "feat(announcements): /unread 与 /read 端点降为仅登录鉴权 — …"
```

---

### Task 9: 前端 —— 管理页搬迁 + 撤卡 + 登录弹窗

**Files:**
- Create: `frontend/src/views/admin/AnnouncementsView.vue`（由 AnnouncementCard.vue 改造）
- Delete: `frontend/src/views/admin/AnnouncementCard.vue`
- Modify: `frontend/src/views/admin/DashboardView.vue`（撤挂载与 import）
- Create: `frontend/src/views/admin/AnnouncementGate.vue`
- Modify: `frontend/src/layouts/AdminLayout.vue`（挂 Gate + ALL_ITEMS 加一项）
- Modify: `frontend/src/router/routes.ts`（加子路由）
- Modify: `frontend/src/api/index.ts`（unread/markRead）
- Modify: `frontend/src/views/admin/AdminsView.vue`（PERMS hint 文案）

**Interfaces:**
- Consumes: Task 8 的 `/unread`、`/read`；既有 `adminAnnouncementsApi` 四方法、`Announcement`、`renderMd`、`useAuthStore`（`ready`、`can`）。
- Produces: 路由名 `admin-announcements`（path `/admin/announcements`）。

- [ ] **Step 1: API 客户端补两方法**

`frontend/src/api/index.ts` 的 `adminAnnouncementsApi` 内 `remove` 之前插入：

```ts
  unread: () => api<{ items: Announcement[] }>({ url: '/admin/announcements/unread' }),
  markRead: (ids: number[]) => api<{ marked: number }>({ url: '/admin/announcements/read', method: 'post', data: { ids } }),
```

- [ ] **Step 2: 管理页（搬 v1 卡片 UI）**

`git mv frontend/src/views/admin/AnnouncementCard.vue frontend/src/views/admin/AnnouncementsView.vue`
然后按下列 4 点改造（其余代码逐字保留）：
1. 最外层 `<section class="rounded-xl border … p-4">` 换成页级容器：
   `<div>` + 顶部标题行 `<div class="mb-5 flex items-center gap-3"><h1 class="text-2xl font-bold">更新公告</h1><span class="text-xs text-ink-3">{{ items.length }} 条</span><n-button class="ml-auto" …>＋ 新建</n-button></div>`，
   列表容器改 `<div class="rounded-xl border border-line bg-surface p-4">` 包裹。
2. 正文限高 `max-h-72` → `max-h-96`。
3. 「0 条」计数与「新建」按钮从原卡头移到标题行（同一批元素，别重复渲染）。
4. 组件名无需改（SFC 文件名即名），`load()` 仍调 `adminAnnouncementsApi.list()`。

- [ ] **Step 3: 撤掉仪表盘挂载**

`DashboardView.vue`：删 `import AnnouncementCard from './AnnouncementsView.vue'`（或原
`AnnouncementCard.vue` 那行）与模板里的 `<AnnouncementCard v-if=… class="mb-5" />` 整行。
`const auth = useAuthStore()` 若撤卡后已无使用者则一并删除（`useAuthStore` 的 import 也删——
注意 `loadAll()` 内部仍在用 `useAuthStore()`，那行保持原样，别把还在用的 import 删掉）。

- [ ] **Step 4: 路由与菜单**

`routes.ts` 在 `columns` 那行之后插入：

```ts
      { path: 'announcements', name: 'admin-announcements', component: () => import('@/views/admin/AnnouncementsView.vue'), meta: { perm: 'announcement:manage' } },
```

`AdminLayout.vue` 的 `ALL_ITEMS`，`栏目管理` 行之后插入（perm 缺省=登录可见，这里要显式管）：

```ts
  { label: '更新公告', key: 'admin-announcements', path: '/admin/announcements', icon: icon('📢'), perm: 'announcement:manage' },
```

- [ ] **Step 5: 登录弹窗组件**

`frontend/src/views/admin/AnnouncementGate.vue`：

```vue
<script setup lang="ts">
import { NModal, useMessage } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'

import { adminAnnouncementsApi } from '@/api'
import type { Announcement } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { renderMd } from '@/composables/useMd'

const message = useMessage()
const auth = useAuthStore()
const items = ref<Announcement[]>([])
const show = ref(false)
let fetched = false      // 一次登录只拉一次：路由来回切不重复打扰

const bodies = computed(() => new Map(items.value.map((i) => [i.id, renderMd(i.body_md).html])))
const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : '')

async function pull() {
  if (fetched) return
  fetched = true
  try {
    items.value = (await adminAnnouncementsApi.unread()).items
    if (items.value.length) show.value = true
  } catch {
    // 弹窗是增益：拉不到就安静跳过，不打断登录流程
  }
}
onMounted(pull)

async function onClose() {
  show.value = false
  const ids = items.value.map((i) => i.id)
  items.value = []
  if (!ids.length) return
  try {
    await adminAnnouncementsApi.markRead(ids)
  } catch {
    message.warning('公告已读状态未能保存，下次登录可能再次看到')
  }
}
</script>

<template>
  <n-modal :show="show" preset="card" title="更新公告"
           :style="{ width: '680px' }" :mask-closable="true"
           @update:show="(v: boolean) => { if (!v) onClose() }">
    <template #header-extra>
      <span class="text-xs text-ink-3">{{ items.length }} 条未读</span>
    </template>
    <div class="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
      <article v-for="it in items" :key="it.id">
        <div class="flex flex-wrap items-baseline gap-2">
          <h3 class="font-bold">{{ it.title }}</h3>
          <span class="text-xs text-ink-3">{{ fmtDate(it.published_at ?? it.created_at) }}
            <template v-if="it.created_by"> · {{ it.created_by }}</template></span>
        </div>
        <div v-if="it.body_md" class="prose mt-1 text-sm" v-html="bodies.get(it.id)" />
      </article>
    </div>
    <template #footer>
      <div class="flex justify-end">
        <button class="rounded-lg px-4 py-1.5 text-sm text-white" style="background: var(--c-primary)"
                @click="onClose">我知道了</button>
      </div>
    </template>
  </n-modal>
</template>
```

实现注意：
- `onClose` 可能被触发两次（点 × 走 `@update:show`、点「我知道了」直接调 `onClose`）——
  第二次 `ids` 已空故不会重复上报，但 `show.value = false` 重复赋值无害。保持现状即可，
  别加额外 flag（YAGNI）。
- `fetched` 用普通 `let` 而非 `ref`：它不参与渲染。

- [ ] **Step 6: 挂进 AdminLayout**

`AdminLayout.vue`：script 里 `import AnnouncementGate from './AnnouncementGate.vue'`（该文件在
`views/admin/`，故路径为 `'../views/admin/AnnouncementGate.vue'`——按文件实际相对位置写）。
模板在 `<div class="admin-root">` 内、`<n-layout has-sider …>` **之前**插入：

```html
          <AnnouncementGate />
```

（必须在 `n-message-provider` 之内，否则 `useMessage()` 抛错。）

- [ ] **Step 7: 类型检查**

Run: `cd frontend && npx vue-tsc -b` → exit 0。

- [ ] **Step 8: 浏览器退出门（controller 执行）**

见 spec §5 的七项。

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src
git commit -m "feat(announcements): 独立管理页 + 全员登录弹窗，撤除仪表盘内嵌卡 — …"
```
（`git add -A frontend/src` 会带上删除的 AnnouncementCard.vue；提交后 `git status --porcelain=v1` 必须干净，且 `git show --stat` 里确认 AnnouncementCard 是 deleted 而非残留。）

---

### Task 10: 文档同步（v2）+ 全量回归

- `docs/backend-architecture.md`：§4.1 补 `announcement_reads` 表行；§5.1 权限点语义改「`announcement:manage` = 可写公告，读全员开放」。
- `docs/frontend-design.md`：Flow H 的 H4 段改为「已撤除」并新开一节写管理页 + 登录弹窗（含「一次登录只弹一次」「关闭即整批标已读」「拉取失败静默」三条口径）。
- `docs/api-reference.md`：§6.5 补 `GET /unread`、`POST /read`（标注仅登录）；§9 速查表把「仪表盘公告卡」改为「公告管理页 + 登录弹窗」。
- 回归：`pytest tests -q` 全绿、`npx vue-tsc -b` exit 0。
