import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.deps import AdminContext
from app.core.permissions import PERMISSIONS
from app.models import Content, MediaAsset, User


async def _login(client, username: str, password: str) -> str:
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


async def _me(client) -> dict:
    r = await client.get("/api/v1/admin/auth/me")
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---------- /admin/auth/me 权限载荷 ----------

async def test_me_exposes_super_flag_and_full_permissions(auth):
    d = await _me(auth)
    assert d["is_super"] is True
    assert d["is_active"] is True
    assert set(d["permissions"]) == set(PERMISSIONS)
    assert d["scoped_column_ids"] == []


async def test_me_staff_sees_only_granted_permissions(auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "media:write"},
                                       {"permission": "content:write", "column_id": 7}])
    token = await _login(auth, "staff1", "staff-pass-123")
    auth.headers["Authorization"] = f"Bearer {token}"
    d = await _me(auth)
    assert d["is_super"] is False
    assert d["permissions"] == ["content:write", "media:write"]
    assert d["scoped_column_ids"] == [7]


# ---------- 建号 ----------

async def test_create_staff_then_listed_with_grants(auth, make_staff):
    made = await make_staff("editor_a", nickname="A 编辑",
                            grants=[{"permission": "content:write", "column_id": 1}])
    assert made["username"] == "editor_a"
    assert made["role"] == "staff"
    rows = (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]
    row = next(r for r in rows if r["username"] == "editor_a")
    assert row["nickname"] == "A 编辑"
    assert row["is_active"] is True
    assert row["content_count"] == 0
    assert row["grants"] == [{"permission": "content:write", "column_id": 1}]


async def test_create_staff_rejects_duplicate_username(auth, make_staff):
    await make_staff("dup")
    r = await auth.post("/api/v1/admin/admins",
                        json={"username": "dup", "password": "good-pass-123",
                              "email": "another@example.test"})
    assert r.json()["code"] == 40900


async def test_create_staff_rejects_weak_passwords(auth):
    for bad in ("short1", "alllettersonly", "1234567890"):
        r = await auth.post("/api/v1/admin/admins",
                            json={"username": f"u{len(bad)}x", "password": bad,
                            "email": f"u{len(bad)}x@example.test"})
        assert r.json()["code"] == 42200, bad


async def test_create_admin_requires_email(auth):
    r = await auth.post("/api/v1/admin/admins",
                        json={"username": "no_mail", "password": "staff-pass-123"})
    assert r.status_code == 422 and r.json()["code"] == 42200


async def test_create_admin_rejects_malformed_email(auth):
    for bad in ("not-an-email", "a@b", "@x.com", "a b@c.com"):
        r = await auth.post("/api/v1/admin/admins", json={
            "username": f"m_{abs(hash(bad)) % 9999}", "password": "staff-pass-123", "email": bad})
        assert r.json()["code"] == 42200, bad


async def test_email_is_normalized_and_returned(auth, make_staff):
    made = await make_staff("mixed_case", email="  Mixed.Case@Example.TEST ")
    assert made["email"] == "mixed.case@example.test"
    row = next(x for x in (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]
               if x["username"] == "mixed_case")
    assert row["email"] == "mixed.case@example.test"


async def test_email_must_be_unique_across_accounts(auth, make_staff):
    await make_staff("first", email="shared@example.test")
    r = await auth.post("/api/v1/admin/admins", json={
        "username": "second", "password": "staff-pass-123",
        "email": "SHARED@example.test "})          # 大小写/空格归一后仍算重复
    assert r.status_code == 409 and r.json()["code"] == 40900
    assert "first" in r.json()["message"]          # 告诉你被谁占了


async def test_email_can_be_updated_and_conflicts_are_blocked(auth, make_staff):
    a = await make_staff("staff_a", email="a@example.test")
    await make_staff("staff_b", email="b@example.test")
    r = await auth.put(f"/api/v1/admin/admins/{a['id']}", json={"email": "c@example.test"})
    assert r.status_code == 200 and r.json()["data"]["email"] == "c@example.test"
    assert (await auth.put(f"/api/v1/admin/admins/{a['id']}",
                           json={"email": "b@example.test"})).json()["code"] == 40900
    # 改回自己原有值不该被判重复
    assert (await auth.put(f"/api/v1/admin/admins/{a['id']}",
                           json={"email": "C@Example.test"})).status_code == 200


async def test_create_staff_rejects_unknown_permission(auth):
    r = await auth.post("/api/v1/admin/admins", json={
        "username": "editor_b", "password": "staff-pass-123", "email": "eb@example.test",
        "grants": [{"permission": "content:explode"}]})
    assert r.json()["code"] == 40000


async def test_column_scope_rejected_for_unscoped_permission(auth):
    r = await auth.post("/api/v1/admin/admins", json={
        "username": "editor_c", "password": "staff-pass-123", "email": "ec@example.test",
        "grants": [{"permission": "log:view", "column_id": 2}]})
    assert r.json()["code"] == 40000


# ---------- 账号管理权限本身 ----------

async def test_staff_without_admin_manage_cannot_open_admins(auth, make_staff):
    await make_staff("staff1")
    token = await _login(auth, "staff1", "staff-pass-123")
    auth.headers["Authorization"] = f"Bearer {token}"
    r = await auth.get("/api/v1/admin/admins")
    assert r.status_code == 403
    assert r.json()["code"] == 40300


async def test_grant_admin_manage_lowers_the_wall(auth, make_staff):
    admin_id = (await _me(auth))["id"]
    await make_staff("super_helper")
    helper = (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]
    helper_id = next(x["id"] for x in helper if x["username"] == "super_helper")
    r = await auth.put(f"/api/v1/admin/admins/{helper_id}/grants",
                       json={"grants": [{"permission": "admin:manage"}]})
    assert r.status_code == 200, r.text
    token = await _login(auth, "super_helper", "staff-pass-123")
    auth.headers["Authorization"] = f"Bearer {token}"
    assert (await auth.get("/api/v1/admin/admins")).status_code == 200
    # 但被授权者仍不是 super
    assert (await _me(auth))["is_super"] is False
    assert admin_id


# ---------- 启停与即时生效 ----------

async def test_deactivated_account_existing_token_is_rejected(auth, make_staff):
    made = await make_staff("staff1")
    token = await _login(auth, "staff1", "staff-pass-123")
    r = await auth.put(f"/api/v1/admin/admins/{made['id']}", json={"is_active": False})
    assert r.status_code == 200, r.text
    auth.headers["Authorization"] = f"Bearer {token}"
    assert (await auth.get("/api/v1/admin/auth/me")).status_code == 401
    assert (await auth.post("/api/v1/admin/auth/login",
                            json={"username": "staff1", "password": "staff-pass-123"})
            ).json()["code"] == 40100


async def test_deactivated_account_cannot_refresh_token(client, auth, make_staff):
    """「停用即时生效」必须连 refresh 通道一起封：不能只让 access 失效而留着换发口。"""
    made = await make_staff("staff1")
    login = await client.post("/api/v1/admin/auth/login",
                              json={"username": "staff1", "password": "staff-pass-123"})
    refresh = login.json()["data"]["refresh_token"]
    assert (await client.post("/api/v1/admin/auth/refresh",
                              json={"refresh_token": refresh})).status_code == 200
    r = await auth.put(f"/api/v1/admin/admins/{made['id']}", json={"is_active": False})
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/admin/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401 and r.json()["code"] == 40100
    assert "停用" in r.json()["message"]


async def test_password_set_via_update_is_logged_as_warning(client, auth, make_staff, caplog):
    """直接设口令与停用/降级同属账号级敏感动作，日志必须落在 warning 档并留痕是谁改的。"""
    made = await make_staff("staff1")
    with caplog.at_level("INFO", logger="pw.app"):
        r = await auth.put(f"/api/v1/admin/admins/{made['id']}", json={"password": "new-pass-1234"})
    assert r.status_code == 200, r.text
    hit = [x for x in caplog.records if "staff1" in x.getMessage() and "password" in x.getMessage()]
    assert hit, [x.getMessage() for x in caplog.records]
    assert hit[-1].levelname == "WARNING"
    assert (await auth.post("/api/v1/admin/auth/login",
                            json={"username": "staff1", "password": "new-pass-1234"})
            ).status_code == 200


async def test_grants_update_is_overwrite_not_additive(auth, make_staff):
    made = await make_staff("staff1", grants=[{"permission": "content:write"},
                                              {"permission": "media:write"}])
    token = await _login(auth, "staff1", "staff-pass-123")
    auth.headers["Authorization"] = f"Bearer {token}"
    assert set((await _me(auth))["permissions"]) == {"content:write", "media:write"}
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'admin', 'test-pass-123')}"
    await auth.put(f"/api/v1/admin/admins/{made['id']}/grants",
                   json={"grants": [{"permission": "comment:moderate"}]})
    auth.headers["Authorization"] = f"Bearer {token}"
    d = await _me(auth)
    assert d["permissions"] == ["comment:moderate"]   # 撤权实时生效，无需重新登录


async def test_grant_update_can_scope_to_a_column(auth, make_staff):
    """后台「编辑账号」那条路：给已有 staff 把权限改成限定指定栏目。

    建号路径的 column_id 早就有测试钉着，更新路径没有 —— 用户报「顶级管理员无法为其他管理员
    分配可编辑的指定栏目」时得先能证明后端本来就存得进去（结论：存得进，卡点在界面）。
    """
    from app.core.db import SessionLocal
    from app.models import Column
    made = await make_staff("staff1", grants=[{"permission": "content:write"}])   # 先给全站
    async with SessionLocal() as db:
        col = Column(name="只放开这栏", slug="only-this", type="article")
        db.add(col)
        await db.commit()
        cid = col.id
    staff_token = await _login(auth, "staff1", "staff-pass-123")
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'admin', 'test-pass-123')}"
    want = [{"permission": "content:write", "column_id": cid}]
    r = await auth.put(f"/api/v1/admin/admins/{made['id']}/grants", json={"grants": want})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["grants"] == want
    rows = (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]
    assert next(x for x in rows if x["id"] == made["id"])["grants"] == want
    auth.headers["Authorization"] = f"Bearer {staff_token}"
    d = await _me(auth)
    assert d["permissions"] == ["content:write"] and d["scoped_column_ids"] == [cid]


# ---------- 护栏 ----------

async def test_last_active_super_cannot_be_deactivated_or_demoted(auth):
    """规则 A：最后一个可用 super 不可停用、不可降级（409，防全站失去顶级管理员）。"""
    admin_id = (await _me(auth))["id"]
    assert (await auth.put(f"/api/v1/admin/admins/{admin_id}",
                           json={"is_active": False})).json()["code"] == 40900
    assert (await auth.put(f"/api/v1/admin/admins/{admin_id}",
                           json={"role": "staff"})).json()["code"] == 40900


async def test_self_deactivation_rejected_when_a_second_super_exists(auth, make_staff):
    """规则 B：即便还有别的 super，也不能停用/降级自己（403，防误操作自锁）。"""
    await make_staff("co_super")
    co_id = next(x["id"] for x in (await auth.get("/api/v1/admin/admins")
                                   ).json()["data"]["items"] if x["username"] == "co_super")
    assert (await auth.put(f"/api/v1/admin/admins/{co_id}", json={"role": "super"})).status_code == 200
    admin_id = (await _me(auth))["id"]
    assert (await auth.put(f"/api/v1/admin/admins/{admin_id}",
                           json={"is_active": False})).json()["code"] == 40300
    assert (await auth.put(f"/api/v1/admin/admins/{admin_id}",
                           json={"role": "staff"})).json()["code"] == 40300


async def test_super_can_update_own_identity_fields_but_not_own_grants(auth):
    """账号页「编辑账号」必须能给自己填邮箱 —— 忘记密码只往 users.email 投递，
    而「我的资料」不含邮箱：这里禁着，顶级管理员就没有任何界面可填。
    权限区不在放行范围内：set_grants 对自己 403、对 super 409，弹窗必须跳过那一步。"""
    me = await _me(auth)
    r = await auth.put(f"/api/v1/admin/admins/{me['id']}",
                       json={"nickname": "站长本人", "email": " Owner@Example.test ", "note": "站点负责人"})
    assert r.status_code == 200, r.text
    row = next(x for x in (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]
               if x["id"] == me["id"])
    assert row["nickname"] == "站长本人" and row["note"] == "站点负责人"
    assert row["email"] == "owner@example.test"        # 粘贴带空格/大写照样归一
    # 权限区必须跳过：super 目标先撞「隐式拥有全部权限」的 409（staff 改自己才是 403，
    # 由 test_admin_manage_grantee_cannot_self_grant 钉住）
    assert (await auth.put(f"/api/v1/admin/admins/{me['id']}/grants",
                           json={"grants": [{"permission": "content:write"}]})).json()["code"] == 40900


async def test_admin_manage_grantee_cannot_self_grant(auth, make_staff):
    """被下放者不能给自己改权限 —— 授权权只在顶级管理员手里。"""
    me = await make_staff("gatekeeper", grants=[{"permission": "admin:manage"},
                                                {"permission": "content:write"}])
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'gatekeeper', 'staff-pass-123')}"
    r = await auth.put(f"/api/v1/admin/admins/{me['id']}/grants",
                       json={"grants": [{"permission": "admin:manage"},
                                         {"permission": "setting:manage"}]})
    assert r.status_code == 403 and "自己" in r.json()["message"]
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'admin', 'test-pass-123')}"
    row = next(x for x in (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]
               if x["id"] == me["id"])
    assert row["permissions"] == ["admin:manage", "content:write"]   # 原样未动


async def test_admin_manage_grantee_cannot_hand_out_admin_manage(auth, make_staff):
    await make_staff("gatekeeper", grants=[{"permission": "admin:manage"}])
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'gatekeeper', 'staff-pass-123')}"
    r = await auth.post("/api/v1/admin/admins", json={
        "username": "clone", "password": "staff-pass-123", "email": "clone@example.test",
        "grants": [{"permission": "admin:manage"}]})
    assert r.status_code == 403 and "顶级" in r.json()["message"]
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'admin', 'test-pass-123')}"
    names = [x["username"] for x in (await auth.get("/api/v1/admin/admins")).json()["data"]["items"]]
    assert "clone" not in names
    # 建号本身仍可以，只是不带 admin:manage
    assert (await auth.post("/api/v1/admin/admins", json={
        "username": "plain_new", "password": "staff-pass-123", "email": "plain_new@example.test"})).status_code == 200


async def test_admin_manage_grantee_cannot_grant_perm_it_lacks(auth, make_staff):
    """只能授出自己已具备的权限点（admin:manage 本身除外，仅顶级可授）。"""
    victim = await make_staff("victim")
    await make_staff("gatekeeper", grants=[{"permission": "admin:manage"},
                                          {"permission": "content:write"}])
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'gatekeeper', 'staff-pass-123')}"
    r = await auth.put(f"/api/v1/admin/admins/{victim['id']}/grants", json={"grants": [
        {"permission": "content:write"}, {"permission": "setting:manage"}]})
    assert r.status_code == 403 and "没有" in r.json()["message"]
    # 授出自己有的那一项则放行
    r = await auth.put(f"/api/v1/admin/admins/{victim['id']}/grants",
                       json={"grants": [{"permission": "content:write"}]})
    assert r.status_code == 200, r.text


async def test_super_can_grant_admin_manage_and_any_perm(auth, make_staff):
    """对照：顶级管理员不受上述三条限制。"""
    made = await make_staff("staff1")
    r = await auth.put(f"/api/v1/admin/admins/{made['id']}/grants", json={"grants": [
        {"permission": "admin:manage"}, {"permission": "setting:manage"},
        {"permission": "log:view"}]})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["data"]["permissions"]) == ["admin:manage", "log:view", "setting:manage"]


async def test_admin_manage_grantee_cannot_create_or_promote_super(auth, make_staff):
    """admin:manage 下放后仍不能造 super / 升别人为 super（防提权到顶级）。"""
    await make_staff("gatekeeper", grants=[{"permission": "admin:manage"}])
    auth.headers["Authorization"] = f"Bearer {await _login(auth, 'gatekeeper', 'staff-pass-123')}"
    assert (await auth.post("/api/v1/admin/admins", json={
        "username": "esc1", "password": "staff-pass-123", "role": "super", "email": "esc1@example.test"})).json()["code"] == 40300
    target = next(x["id"] for x in (await auth.get("/api/v1/admin/admins")
                                    ).json()["data"]["items"] if x["username"] == "gatekeeper")
    assert (await auth.put(f"/api/v1/admin/admins/{target}",
                           json={"role": "super"})).json()["code"] == 40300
    # 但建普通 staff 仍然可以
    assert (await auth.post("/api/v1/admin/admins", json={
        "username": "esc_ok", "password": "staff-pass-123", "email": "esc_ok@example.test"})).status_code == 200


async def test_delete_blocked_when_account_owns_content(auth, make_staff):
    made = await make_staff("staff1")
    async with SessionLocal() as db:
        db.add(Content(type="article", status="draft", title="占位", slug="hold-1",
                       created_by_id=made["id"]))
        await db.commit()
    assert (await auth.delete(f"/api/v1/admin/admins/{made['id']}")).json()["code"] == 40900
    r = await auth.delete("/api/v1/admin/admins/999999")
    assert r.json()["code"] == 40400


async def test_delete_blocked_when_account_uploaded_media(auth, make_staff):
    made = await make_staff("staff1")
    async with SessionLocal() as db:
        db.add(MediaAsset(filename="a.png", storage_key="2026/10/a.png", kind="image",
                          mime="image/png", size=1, sha256="0" * 64, uploaded_by_id=made["id"]))
        await db.commit()
    assert (await auth.delete(f"/api/v1/admin/admins/{made['id']}")).json()["code"] == 40900


async def test_delete_empty_account_cascades_grants(auth, make_staff):
    made = await make_staff("ghost", grants=[{"permission": "media:write"}])
    assert (await auth.delete(f"/api/v1/admin/admins/{made['id']}")).status_code == 200
    async with SessionLocal() as db:
        assert (await db.get(User, made["id"])) is None


# ---------- 重置口令 ----------

async def test_reset_password_returns_once_and_kills_old_session(auth, make_staff):
    made = await make_staff("staff1")
    token = await _login(auth, "staff1", "staff-pass-123")
    r = await auth.post(f"/api/v1/admin/admins/{made['id']}/reset-password")
    assert r.status_code == 200, r.text
    new_pw = r.json()["data"]["password"]
    assert new_pw != "staff-pass-123"
    auth.headers["Authorization"] = f"Bearer {token}"
    assert (await auth.get("/api/v1/admin/auth/me")).status_code == 401
    assert (await auth.post("/api/v1/admin/auth/login",
                            json={"username": "staff1", "password": new_pw})
            ).status_code == 200


# ---------- AdminContext 判定内核（纯单元，不起 HTTP） ----------

def test_ctx_super_bypasses_without_grant_rows():
    ctx = AdminContext(user=User(id=1, username="admin", role="super"), is_super=True,
                       grants=frozenset())
    assert ctx.can("content:write", column_id=42)
    assert ctx.can("setting:manage")


def test_ctx_global_grant_covers_any_column():
    ctx = AdminContext(user=User(id=2, username="s", role="staff"), is_super=False,
                       grants=frozenset({("content:write", "global", None)}))
    assert ctx.can("content:write", column_id=9)
    assert not ctx.can("content:delete", column_id=9)


def test_ctx_column_scoped_grant_stays_in_its_lane():
    ctx = AdminContext(user=User(id=2, username="s", role="staff"), is_super=False,
                       grants=frozenset({("content:write", "column", 3)}))
    assert ctx.can("content:write", column_id=3)
    assert not ctx.can("content:write", column_id=4)
    assert not ctx.can("content:write")            # 未挂栏目 → 需全局权
    assert not ctx.can("media:write", column_id=3)


def test_ctx_zero_grant_staff_can_write_nothing():
    ctx = AdminContext(user=User(id=2, username="s", role="staff"), is_super=False,
                       grants=frozenset())
    assert not ctx.can("content:write", column_id=1)
    assert not ctx.can("comment:moderate")


@pytest.mark.asyncio
async def test_seed_admin_is_created_as_super():
    from app.services.auth import ensure_admin
    async with SessionLocal() as db:
        u = await ensure_admin(db, "zz-admin", "some-pass-123")
        assert u.role == "super"
        row = (await db.execute(select(User).where(User.username == "zz-admin"))).scalar_one()
        assert row.role == "super" and row.is_active is True
