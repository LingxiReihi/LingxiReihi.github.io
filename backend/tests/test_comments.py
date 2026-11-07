"""评论：先审后显、蜜罐、冷却、批量审核、内容列表计数。"""
import re

from tests.test_public import seed_contents  # noqa: F401


async def _submit(client, content_id, **kw):
    body = {"content_id": content_id, "nickname": "小明",
            "email": "xiaoming@example.com", "body": "写得好！", **kw}
    return await client.post("/api/v1/comments", json=body)


async def test_comment_moderation_flow(client, auth):
    from app.api import comments as cmod
    cmod._submit_cooldown.clear()
    await seed_contents()
    det = (await client.get("/api/v1/posts/post-one")).json()["data"]
    r = await _submit(client, det["id"])
    assert r.status_code == 200 and r.json()["data"]["pending"] is True
    # 未过审：公开列表为空
    lst = (await client.get(f"/api/v1/comments?content_id={det['id']}")).json()["data"]
    assert lst["total"] == 0
    # 后台可见（含邮箱），公开响应不含邮箱
    admin_lst = (await auth.get("/api/v1/admin/comments?status=pending")).json()["data"]
    assert admin_lst["total"] == 1 and admin_lst["pending"] == 1
    c = admin_lst["items"][0]
    assert c["email"] == "xiaoming@example.com" and c["content_title"] == "第一篇文章"
    # 通过 → 前台可见 + 本地开源图包头像，无邮箱字段
    r = await auth.post("/api/v1/admin/comments/moderate", json={"ids": [c["id"]], "status": "approved"})
    assert r.json()["data"]["updated"] == 1
    lst = (await client.get(f"/api/v1/comments?content_id={det['id']}")).json()["data"]
    assert lst["total"] == 1
    pub = lst["items"][0]
    assert "email" not in pub and re.fullmatch(r"/avatars/\d{2}\.svg", pub["avatar"])
    # 拒绝后隐藏
    await auth.post("/api/v1/admin/comments/moderate", json={"ids": [c["id"]], "status": "rejected"})
    lst = (await client.get(f"/api/v1/comments?content_id={det['id']}")).json()["data"]
    assert lst["total"] == 0
    # 删除
    r = await auth.delete(f"/api/v1/admin/comments/{c['id']}")
    assert r.status_code == 200


async def test_comment_honeypot_and_cooldown(client, auth):
    from app.api import comments as cmod
    cmod._submit_cooldown.clear()
    await seed_contents()
    det = (await client.get("/api/v1/posts/post-one")).json()["data"]
    r = await _submit(client, det["id"], website="http://spam")
    assert r.status_code == 200  # 假装成功
    admin_lst = (await auth.get("/api/v1/admin/comments")).json()["data"]
    assert admin_lst["total"] == 0
    # 正常提交后 60s 冷却
    assert (await _submit(client, det["id"])).status_code == 200
    r = await _submit(client, det["id"], body="再来一条")
    assert r.status_code == 429 and r.json()["code"] == 42900
    # 不同内容不共享冷却
    det2 = (await client.get("/api/v1/posts/vue-tips")).json()["data"]
    assert (await _submit(client, det2["id"])).status_code == 200


async def test_comment_validation(client, auth):
    from app.api import comments as cmod
    cmod._submit_cooldown.clear()
    await seed_contents()
    det = (await client.get("/api/v1/posts/post-one")).json()["data"]
    r = await _submit(client, det["id"], email="not-an-email")
    assert r.status_code == 422
    r = await _submit(client, det["id"], body="")
    assert r.status_code == 422
    # 草稿内容 404
    draft = (await auth.post("/api/v1/admin/contents",
                             json={"type": "article", "title": "t", "status": "draft"})).json()["data"]
    assert (await _submit(client, draft["id"])).status_code == 404
    # 杂谈可评（全栏目）
    chats = (await client.get("/api/v1/chats?limit=1")).json()["data"]["items"]
    cmod._submit_cooldown.clear()
    assert (await _submit(client, chats[0]["id"])).status_code == 200


async def test_content_list_comment_count(auth):
    from app.api import comments as cmod
    cmod._submit_cooldown.clear()
    await seed_contents()
    det = (await auth.get("/api/v1/admin/contents?type=article")).json()["data"]
    row = next(x for x in det["items"] if x["slug"] == "post-one")
    assert row["comment_count"] == 0
    # auth 客户端同样可调公开提交接口
    await auth.post("/api/v1/comments", json={
        "content_id": row["id"], "nickname": "n", "email": "a@b.co", "body": "x"})
    det = (await auth.get("/api/v1/admin/contents?type=article")).json()["data"]
    row = next(x for x in det["items"] if x["slug"] == "post-one")
    assert row["comment_count"] == 1
