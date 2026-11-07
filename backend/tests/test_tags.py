"""标签按内容类型隔离：CRUD、解析、删除解绑、公开过滤。"""
import pytest


async def _create(client, name, type_):
    return await client.post("/api/v1/admin/tags", json={"name": name, "type": type_})


@pytest.mark.asyncio
async def test_same_name_across_types(auth):
    r1 = await _create(auth, "Blender", "article")
    r2 = await _create(auth, "Blender", "model")
    assert r1.json()["code"] == 0 and r2.json()["code"] == 0
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]
    dup = await _create(auth, "Blender", "article")
    assert dup.json()["code"] != 0  # 同类型重名仍冲突


@pytest.mark.asyncio
async def test_list_filter_by_type(auth):
    await _create(auth, "技术", "article")
    await _create(auth, "渲染", "model")
    r = await auth.get("/api/v1/admin/tags", params={"type": "model"})
    items = r.json()["data"]["items"]
    assert [t["name"] for t in items] == ["渲染"]
    assert items[0]["type"] == "model"


@pytest.mark.asyncio
async def test_content_tag_resolution_scoped(auth):
    tag = (await _create(auth, "Vue", "article")).json()["data"]
    # 文章用 article 标签：按 id 与按 name 均可
    r = await auth.post("/api/v1/admin/contents", json={
        "type": "article", "title": "A1", "body_md": "x", "status": "draft",
        "tags": [{"id": tag["id"]}, {"name": "新标签"}]})
    assert r.json()["code"] == 0
    tags = r.json()["data"]["tags"]
    assert {t["name"] for t in tags} == {"Vue", "新标签"}
    assert all(t["type"] == "article" for t in tags)
    # 模型内容引用 article 标签 id → 拒绝
    bad = await auth.post("/api/v1/admin/contents", json={
        "type": "model", "title": "M1", "body_md": "x", "status": "draft",
        "tags": [{"id": tag["id"]}]})
    assert bad.json()["code"] != 0
    # 模型同名新建，互不干扰
    m = await auth.post("/api/v1/admin/contents", json={
        "type": "model", "title": "M2", "body_md": "x", "status": "draft", "tags": [{"name": "Vue"}]})
    assert m.json()["code"] == 0
    assert m.json()["data"]["tags"][0]["type"] == "model"


@pytest.mark.asyncio
async def test_delete_detaches(auth):
    tag = (await _create(auth, "临时", "article")).json()["data"]
    await auth.post("/api/v1/admin/contents", json={
        "type": "article", "title": "D1", "body_md": "x", "status": "draft", "tags": [{"id": tag["id"]}]})
    r = await auth.delete(f"/api/v1/admin/tags/{tag['id']}")
    assert r.json()["data"]["detached"] == 1
    lst = (await auth.get("/api/v1/admin/tags", params={"type": "article"})).json()["data"]["items"]
    assert "临时" not in [t["name"] for t in lst]


@pytest.mark.asyncio
async def test_multi_tag_and_filter(auth, client):
    a = (await _create(auth, "甲", "article")).json()["data"]
    b = (await _create(auth, "乙", "article")).json()["data"]
    for title, tgs in (("T1", [a]), ("T2", [a, b]), ("T3", [])):
        r = await auth.post("/api/v1/admin/contents", json={
            "type": "article", "title": title, "body_md": "x", "status": "published",
            "slug": title.lower(), "tags": [{"id": t["id"]} for t in tgs]})
        assert r.json()["code"] == 0
    both = (await client.get("/api/v1/posts", params={"tag": "甲,乙"})).json()["data"]
    assert [i["title"] for i in both["items"]] == ["T2"]
    one = (await client.get("/api/v1/posts", params={"tag": "甲"})).json()["data"]
    assert {i["title"] for i in one["items"]} == {"T1", "T2"}


@pytest.mark.asyncio
async def test_public_tags_type_filter(auth, client):
    tag = (await _create(auth, "公开", "chat")).json()["data"]
    await auth.post("/api/v1/admin/contents", json={
        "type": "chat", "title": "C1", "body_md": "x", "status": "published", "tags": [{"id": tag["id"]}]})
    r = await client.get("/api/v1/tags", params={"type": "chat"})
    items = r.json()["data"]["items"]
    assert items and items[0]["name"] == "公开" and items[0]["type"] == "chat"
    r2 = await client.get("/api/v1/tags", params={"type": "article"})
    assert r2.json()["data"]["items"] == []
