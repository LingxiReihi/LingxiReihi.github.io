"""B2 归属与作用域判定：staff 只能管自己上传的内容，且受栏目作用域约束。"""
import io

from PIL import Image
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import AdminGrant, Column, Comment, Content


async def _login_as(client, username: str, password: str = "staff-pass-123"):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"


async def _admin(client):
    await _login_as(client, "admin", "test-pass-123")


async def _column(client, name: str, type_: str = "article") -> int:
    r = await client.post("/api/v1/admin/columns", json={"name": name, "type": type_})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _content(client, title: str, column_id: int | None = None,
                   type_: str = "article") -> dict:
    body = {"type": type_, "status": "draft", "title": title, "body_md": "正文"}
    if column_id is not None:
        body["column_id"] = column_id
    r = await client.post("/api/v1/admin/contents", json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _png(color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), color).save(buf, "PNG")
    return buf.getvalue()


# ---------- 内容归属 ----------

async def test_created_content_records_owner_and_is_editable(client, auth, make_staff):
    made = await make_staff("staff1", grants=[{"permission": "content:write"}])
    await _login_as(client, "staff1")
    c = await _content(client, "自己的草稿")
    assert c["owner_id"] == made["id"]
    assert c["owner_nickname"] == "staff1"
    assert c["can_edit"] is True and c["can_delete"] is False


async def test_zero_grant_staff_cannot_create_anything(client, auth, make_staff):
    await make_staff("readonly_guy")
    await _login_as(client, "readonly_guy")
    r = await client.post("/api/v1/admin/contents",
                          json={"type": "article", "status": "draft", "title": "x"})
    assert r.status_code == 403
    assert "权限" in r.json()["message"] or "栏目" in r.json()["message"]
    assert (await client.post("/api/v1/admin/media",
                              files={"file": ("a.png", io.BytesIO(await _png()), "image/png")}
                              )).status_code == 403


async def test_staff_can_read_others_content_but_not_edit(client, auth, make_staff):
    mine = await _content(auth, "顶级管理员的内容")
    await make_staff("staff1", grants=[{"permission": "content:write"}])
    await _login_as(client, "staff1")
    r = await client.get(f"/api/v1/admin/contents/{mine['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["can_edit"] is False
    assert "只能管理自己上传" in r.json()["data"]["denied_reason"]
    for verb, url in (("put", f"/api/v1/admin/contents/{mine['id']}"),
                      ("patch", f"/api/v1/admin/contents/{mine['id']}/status")):
        r = await getattr(client, verb)(url, json={"title": "改写别人"} if verb == "put"
                                        else {"status": "published"})
        assert r.status_code == 403, (verb, r.text)
        assert "只能管理自己上传" in r.json()["message"]
    assert (await client.delete(f"/api/v1/admin/contents/{mine['id']}")).status_code == 403


async def test_list_marks_can_edit_per_row_and_mine_filter(client, auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "content:write"},
                                       {"permission": "content:delete"}])
    await _login_as(client, "staff1")
    mine = await _content(client, "staff 的内容")
    await _admin(client)
    theirs = await _content(client, "admin 的内容")
    await _login_as(client, "staff1")
    rows = {r["id"]: r for r in (await client.get("/api/v1/admin/contents")).json()["data"]["items"]}
    assert rows[mine["id"]]["can_edit"] is True and rows[mine["id"]]["can_delete"] is True
    assert rows[theirs["id"]]["can_edit"] is False
    only_mine = (await client.get("/api/v1/admin/contents?mine=1")).json()["data"]
    assert {r["id"] for r in only_mine["items"]} == {mine["id"]}
    assert only_mine["total"] == 1


async def test_super_row_always_editable(client, auth):
    await _admin(client)
    rows = (await client.get("/api/v1/admin/contents")).json()["data"]["items"]
    assert all(r["can_edit"] and r["can_delete"] for r in rows)


# ---------- 栏目作用域 ----------

async def test_column_scoped_grant_limits_where_content_lives(client, auth, make_staff):
    col_a = await _column(auth, "A 栏目")
    col_b = await _column(auth, "B 栏目")
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col_a}])
    await _login_as(client, "staff1")
    ok = await _content(client, "落在授权栏目", col_a)
    assert ok["column"]["id"] == col_a
    r = await client.post("/api/v1/admin/contents",
                          json={"type": "article", "status": "draft", "title": "越界",
                                "column_id": col_b})
    assert r.status_code == 403 and "栏目" in r.json()["message"]
    # 未挂栏目需要全局权
    r = await client.post("/api/v1/admin/contents",
                          json={"type": "article", "status": "draft", "title": "无栏目"})
    assert r.status_code == 403 and "栏目" in r.json()["message"]


async def test_moving_own_content_out_of_granted_column_is_denied(client, auth, make_staff):
    col_a = await _column(auth, "A 栏目")
    col_b = await _column(auth, "B 栏目")
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col_a}])
    await _login_as(client, "staff1")
    c = await _content(client, "自己的稿子", col_a)
    r = await client.put(f"/api/v1/admin/contents/{c['id']}", json={"column_id": col_b})
    assert r.status_code == 403 and "栏目" in r.json()["message"]
    # 移到无栏目同样需要全局权
    assert (await client.put(f"/api/v1/admin/contents/{c['id']}",
                             json={"column_id": None})).status_code == 403
    # 留在原栏目内可以
    r = await client.put(f"/api/v1/admin/contents/{c['id']}", json={"title": "改标题"})
    assert r.status_code == 200, r.text


async def test_column_bulk_skips_foreign_and_unauthorized(client, auth, make_staff):
    col_a = await _column(auth, "A 栏目")
    mine = await _content(auth, "admin 的内容")          # 归属 admin，staff 改不动
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col_a}])
    await _login_as(client, "staff1")
    own = await _content(client, "staff 的内容", col_a)
    r = await client.post("/api/v1/admin/contents/column-bulk",
                          json={"ids": [own["id"], mine["id"]], "column_id": col_a})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["updated"] == 1 and d["denied"] == [mine["id"]]


async def test_delete_requires_content_delete_grant(client, auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "content:write"}])
    await _login_as(client, "staff1")
    c = await _content(client, "待删")
    assert (await client.delete(f"/api/v1/admin/contents/{c['id']}")).status_code == 403
    await _admin(client)
    uid = next(x["id"] for x in (await client.get("/api/v1/admin/admins")
                                 ).json()["data"]["items"] if x["username"] == "staff1")
    await client.put(f"/api/v1/admin/admins/{uid}/grants",
                     json={"grants": [{"permission": "content:write"},
                                      {"permission": "content:delete"}]})
    await _login_as(client, "staff1")
    assert (await client.delete(f"/api/v1/admin/contents/{c['id']}")).status_code == 200


async def test_reset_likes_requires_ownership(client, auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "content:write"}])
    theirs = await _content(auth, "admin 的稿子")
    await _login_as(client, "staff1")
    assert (await client.post(f"/api/v1/admin/contents/{theirs['id']}/reset-likes")
            ).status_code == 403
    mine = await _content(client, "staff 的稿子")
    assert (await client.post(f"/api/v1/admin/contents/{mine['id']}/reset-likes")
            ).status_code == 200


# ---------- 素材 ----------

async def test_media_upload_records_uploader_and_scopes_delete(client, auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "media:write"}])
    await _login_as(client, "staff1")
    r = await client.post("/api/v1/admin/media",
                          files={"file": ("staff.png", io.BytesIO(await _png()), "image/png")})
    assert r.status_code == 200, r.text
    a = r.json()["data"]
    assert a["uploader_id"] == (await client.get("/api/v1/admin/auth/me")).json()["data"]["id"]
    assert a["can_delete"] is False          # 有 media:write 但没有 media:delete
    rows = (await client.get("/api/v1/admin/media")).json()["data"]["items"]
    assert any(x["id"] == a["id"] and x["uploader_nickname"] == "staff1" for x in rows)
    assert (await client.delete(f"/api/v1/admin/media/{a['id']}")).status_code == 403

    await _admin(client)
    admin_asset = (await client.post("/api/v1/admin/media",
                                     files={"file": ("admin.png", io.BytesIO(await _png((0, 0, 255))),
                                                     "image/png")})).json()["data"]
    await _login_as(client, "staff1")
    assert (await client.delete(f"/api/v1/admin/media/{admin_asset['id']}")).status_code == 403
    # mine=1 只看自己上传的
    only = (await client.get("/api/v1/admin/media?mine=1")).json()["data"]
    assert [x["id"] for x in only["items"]] == [a["id"]]


async def test_media_delete_with_grant_and_reference_protection(client, auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "media:write"},
                                       {"permission": "media:delete"},
                                       {"permission": "content:write"}])
    await _login_as(client, "staff1")
    a = (await client.post("/api/v1/admin/media",
                           files={"file": ("own.png", io.BytesIO(await _png()), "image/png")}
                           )).json()["data"]
    assert (await client.delete(f"/api/v1/admin/media/{a['id']}")).status_code == 200
    b = (await client.post("/api/v1/admin/media",
                           files={"file": ("used.png", io.BytesIO(await _png((0, 255, 0))),
                                           "image/png")})).json()["data"]
    c = await _content(client, "引用封面", None)
    await client.put(f"/api/v1/admin/contents/{c['id']}", json={"cover_asset_id": b["id"]})
    r = await client.delete(f"/api/v1/admin/media/{b['id']}")
    assert r.status_code == 409 and "引用" in r.json()["message"]


# ---------- 评论：全站共享队列（归属隔离的显式例外） ----------

async def test_comment_moderation_is_site_wide_and_leaves_trace(client, auth, make_staff):
    c = await _content(auth, "admin 的内容")          # 内容归 admin
    uid = (await make_staff("staff1", grants=[{"permission": "comment:moderate"}]))["id"]
    async with SessionLocal() as db:
        db.add(Comment(content_id=c["id"], nickname="路人", email="a@b.com", body="顶一下",
                       status="pending"))
        await db.commit()
        cid = (await db.execute(select(Comment.id).where(Comment.content_id == c["id"]))
               ).scalar_one()
    await _login_as(client, "staff1")
    r = await client.post("/api/v1/admin/comments/moderate",
                          json={"ids": [cid], "status": "approved"})
    assert r.status_code == 200, r.text        # 不因归属被拒
    async with SessionLocal() as db:
        row = (await db.execute(select(Comment).where(Comment.id == cid))).scalar_one()
        assert row.reviewed_by_id == uid and row.status == "approved"
    assert (await client.delete(f"/api/v1/admin/comments/{cid}")).status_code == 200


async def test_categorize_only_touches_own_assets(client, auth, make_staff):
    """改分类会写库（标签）→ 属于写操作，必须按归属隔离。"""
    admin_asset = (await auth.post("/api/v1/admin/media",
                                   files={"file": ("admin-own.png", io.BytesIO(await _png((0, 0, 255))),
                                                   "image/png")})).json()["data"]
    await make_staff("staff1", grants=[{"permission": "media:write"}])
    await _login_as(client, "staff1")
    mine = (await client.post("/api/v1/admin/media",
                              files={"file": ("mine.png", io.BytesIO(await _png()), "image/png")}
                              )).json()["data"]
    r = await client.post("/api/v1/admin/media/categorize",
                          json={"ids": [mine["id"], admin_asset["id"]], "category": "avatar"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["updated"] == 1 and d["denied"] == [admin_asset["id"]]
    await _admin(client)
    rows = {a["id"]: a for a in (await client.get("/api/v1/admin/media")).json()["data"]["items"]}
    assert rows[admin_asset["id"]]["category"] == "blog"   # 别人的素材纹丝不动
    assert rows[mine["id"]]["category"] == "avatar"


async def test_categorize_foreign_only_is_fully_denied(client, auth, make_staff):
    await make_staff("staff1", grants=[{"permission": "media:write"}])
    await _login_as(client, "staff1")
    r = await client.post("/api/v1/admin/media/categorize",
                          json={"ids": [1], "category": "avatar"})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"updated": 0, "denied": [1]}


async def test_column_bulk_cannot_move_into_ungranted_column(client, auth, make_staff):
    """目标栏目也要过作用域：PUT 单条已拦，批量路径不能开后门。"""
    col_a = await _column(auth, "A 栏目")
    col_b = await _column(auth, "B 栏目")
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col_a}])
    await _login_as(client, "staff1")
    own = await _content(client, "A 栏目的自家稿", col_a)
    r = await client.post("/api/v1/admin/contents/column-bulk",
                          json={"ids": [own["id"]], "column_id": col_b})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["updated"] == 0 and d["denied"] == [own["id"]]
    assert (await client.get(f"/api/v1/admin/contents/{own['id']}")).json()["data"]["column"]["id"] == col_a


async def test_column_bulk_between_two_granted_columns_allowed(client, auth, make_staff):
    """起点与终点都在授权范围内 → 放行。"""
    col_a = await _column(auth, "A 栏目")
    col_c = await _column(auth, "C 栏目")
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col_a},
                                       {"permission": "content:write", "column_id": col_c}])
    await _login_as(client, "staff1")
    own = await _content(client, "两个栏目都授权", col_a)
    r = await client.post("/api/v1/admin/contents/column-bulk",
                          json={"ids": [own["id"]], "column_id": col_c})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"updated": 1, "skipped": 0, "denied": []}


async def test_column_bulk_out_of_granted_column_denied(client, auth, make_staff):
    """从被授权栏目里「移出」同样是跨作用域写入。"""
    col_a = await _column(auth, "A 栏目")
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col_a}])
    await _login_as(client, "staff1")
    own = await _content(client, "待移出的稿子", col_a)
    r = await client.post("/api/v1/admin/contents/column-bulk", json={"ids": [own["id"]], "column_id": None})
    assert r.json()["data"]["denied"] == [own["id"]]


async def test_comment_moderation_requires_the_permission(client, auth, make_staff):
    await make_staff("staff1")
    await _login_as(client, "staff1")
    assert (await client.post("/api/v1/admin/comments/moderate",
                              json={"ids": [1], "status": "approved"})).status_code == 403
    assert (await client.delete("/api/v1/admin/comments/1")).status_code == 403


# ---------- 栏目/标签/设置/日志/统计 ----------

async def test_tag_and_setting_and_log_and_stats_gates(client, auth, make_staff):
    await make_staff("staff1")
    await _login_as(client, "staff1")
    assert (await client.post("/api/v1/admin/tags", json={"name": "新标签", "type": "article"})
            ).status_code == 403
    assert (await client.put("/api/v1/admin/settings/site", json={"title": "x"})
            ).status_code == 403
    assert (await client.get("/api/v1/admin/logs/files")).status_code == 403
    assert (await client.get("/api/v1/admin/stats/overview")).status_code == 403
    assert (await client.post("/api/v1/admin/seo/push", json={"urls": []})).status_code == 403
    assert (await client.get("/api/v1/admin/tags")).status_code == 200   # 读不受限

    await _admin(client)
    uid = next(x["id"] for x in (await client.get("/api/v1/admin/admins")
                                 ).json()["data"]["items"] if x["username"] == "staff1")
    await client.put(f"/api/v1/admin/admins/{uid}/grants", json={"grants": [
        {"permission": "tag:manage"}, {"permission": "setting:manage"},
        {"permission": "log:view"}, {"permission": "stats:view"}]})
    await _login_as(client, "staff1")
    assert (await client.post("/api/v1/admin/tags", json={"name": "新标签", "type": "article"})
            ).status_code == 200
    assert (await client.put("/api/v1/admin/settings/site", json={"title": "x"})).status_code == 200
    assert (await client.get("/api/v1/admin/logs/files")).status_code == 200
    assert (await client.get("/api/v1/admin/stats/overview")).status_code == 200
    # SEO 推送与重建是站点级动作，仍只归 super
    assert (await client.post("/api/v1/admin/seo/push", json={"urls": []})).status_code == 403


async def test_column_manage_gates_and_list_marks_can_manage(client, auth, make_staff):
    col_a = await _column(auth, "A 栏目")
    await make_staff("staff1", grants=[{"permission": "column:manage", "column_id": col_a}])
    await _login_as(client, "staff1")
    rows = {r["id"]: r for r in (await client.get("/api/v1/admin/columns")).json()["data"]["items"]}
    assert rows[col_a]["can_manage"] is True
    assert all(v["can_manage"] is False for k, v in rows.items() if k != col_a)
    assert (await client.put(f"/api/v1/admin/columns/{col_a}", json={"name": "改名"})).status_code == 200
    await _admin(client)
    other = await _column(client, "C 栏目")
    await _login_as(client, "staff1")
    assert (await client.put(f"/api/v1/admin/columns/{other}", json={"name": "越权"})).status_code == 403
    assert (await client.post("/api/v1/admin/columns", json={"name": "新栏目"})).status_code == 403


async def test_delete_column_needs_global_manage_when_it_holds_others_content(client, auth, make_staff):
    """删栏目会把栏目下所有人的内容 column_id 置空 → 属跨归属写入，栏目级授权不够。"""
    col = await _column(auth, "有人居住的栏目")
    await _content(auth, "admin 的稿子", col)          # 归 admin
    uid = (await make_staff("staff1", grants=[{"permission": "column:manage", "column_id": col}]))["id"]
    await _login_as(client, "staff1")
    r = await client.delete(f"/api/v1/admin/columns/{col}")
    assert r.status_code == 403 and "全局" in r.json()["message"]
    async with SessionLocal() as db:
        assert (await db.execute(select(Column).where(Column.id == col))).scalar_one() is not None
        assert (await db.execute(select(Content.column_id).where(Content.column_id == col))).first() is not None

    # 自己上传的内容不阻挡：清空他人内容后即可删
    await _admin(client)
    await client.put(f"/api/v1/admin/admins/{uid}/grants",
                     json={"grants": [{"permission": "column:manage"}]})
    await _login_as(client, "staff1")
    assert (await client.delete(f"/api/v1/admin/columns/{col}")).status_code == 200


async def test_delete_column_of_only_own_content_allowed_with_scoped_grant(client, auth, make_staff):
    col = await _column(auth, "只有我住")
    uid = (await make_staff("staff1", grants=[{"permission": "content:write"},
                                              {"permission": "column:manage", "column_id": col}]))["id"]
    await _login_as(client, "staff1")
    own = await _content(client, "自家稿子", col)
    # 先把自己内容删掉（需 content:delete）→ 栏目空 → 栏目级授权足以删栏目
    await _admin(client)
    await client.put(f"/api/v1/admin/admins/{uid}/grants", json={"grants": [
        {"permission": "content:write"}, {"permission": "content:delete"},
        {"permission": "column:manage", "column_id": col}]})
    await _login_as(client, "staff1")
    assert (await client.delete(f"/api/v1/admin/contents/{own['id']}")).status_code == 200
    assert (await client.delete(f"/api/v1/admin/columns/{col}")).status_code == 200


async def test_put_cannot_reassign_ownership_type_or_counters(client, auth, make_staff):
    """PUT 的 setattr 循环只能碰 DTO 里声明的字段：归属、类型、计数不可被客户端写入。
    这条钉子防的是将来给 ContentPatch 加 type 字段或改 extra='allow' 后，
    staff 借「改自己内容」的名义把内容转给别人 / 跨栏目类型乱挪 / 刷计数。"""
    made = await make_staff("staff1", grants=[{"permission": "content:write"}])
    await _login_as(client, "staff1")
    own = await _content(client, "自家稿子")
    r = await client.put(f"/api/v1/admin/contents/{own['id']}", json={
        "title": "改个标题", "created_by_id": 1, "owner_id": 1, "type": "model",
        "likes": 999, "view_count": 12345, "column_id": own["column_id"]})
    assert r.status_code == 200, r.text
    d = (await client.get(f"/api/v1/admin/contents/{own['id']}")).json()["data"]
    assert d["title"] == "改个标题"
    assert d["owner_id"] == made["id"], "归属被改写"
    assert d["type"] == "article", "类型被改写"
    assert d["likes"] == 0 and d["view_count"] == 0, "计数被客户端写入"


async def test_create_ignores_client_supplied_owner_and_counters(client, auth, make_staff):
    """新建同理：归属由服务端按登录者写死，不接受客户端传入。"""
    await make_staff("staff1", grants=[{"permission": "content:write"}])
    await _login_as(client, "staff1")
    me = (await client.get("/api/v1/admin/auth/me")).json()["data"]
    c = await _content(client, "伪造归属的草稿")
    body = {"type": "article", "status": "draft", "title": "伪造归属二",
            "created_by_id": 1, "likes": 500}
    r = await client.post("/api/v1/admin/contents", json=body)
    d = r.json()["data"]
    assert d["owner_id"] == me["id"] and d["likes"] == 0
    assert c["owner_id"] == me["id"]


def test_content_dto_drops_fields_outside_the_contract():
    """归属不变式的机制根：PUT/新建的 setattr 只会吃 DTO 里声明过的字段。
    哪天给这两个 schema 开了 extra='allow'、或加了 type/created_by_id/计数字段，这条立刻红。"""
    from app.schemas.admin import ContentPatch, ContentUpsert

    patched = ContentPatch.model_validate({
        "title": "改标题", "created_by_id": 1, "owner_id": 1, "type": "model",
        "likes": 9, "view_count": 9, "id": 7, "status": "draft"})
    dumped = patched.model_dump(exclude_unset=True)
    assert set(dumped) <= {"status", "title", "slug", "summary", "body_md", "cover_asset_id",
                           "media_kind", "tags", "extra", "asset_ids", "column_id"}
    for forbidden in ("created_by_id", "owner_id", "type", "likes", "view_count", "id"):
        assert dumped.get(forbidden) is None, f"ContentPatch 竟然接收了 {forbidden}"

    created = ContentUpsert.model_validate({
        "type": "article", "title": "新稿", "created_by_id": 1, "likes": 3, "view_count": 8})
    for forbidden in ("created_by_id", "likes", "view_count"):
        assert forbidden not in created.model_dump(), f"ContentUpsert 竟然接收了 {forbidden}"


async def test_deleting_column_clears_scoped_grants(client, auth, make_staff):
    col = await _column(auth, "要删掉的栏目")
    await make_staff("staff1", grants=[{"permission": "content:write", "column_id": col}])
    await _login_as(client, "staff1")
    await _content(client, "栏目里的稿子", col)
    await _admin(client)
    assert (await client.delete(f"/api/v1/admin/columns/{col}")).status_code == 200
    async with SessionLocal() as db:
        assert (await db.execute(select(AdminGrant).where(AdminGrant.scope_id == col))
                ).scalars().all() == []
