"""素材库整理：重命名 / 改分类都不动 URL，按内容自动分组与筛选。"""
import io

from PIL import Image


async def _png(color=(10, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), color).save(buf, "PNG")
    return buf.getvalue()


async def _upload(auth, name="pic.png", color=(10, 120, 200), category="blog") -> dict:
    r = await auth.post("/api/v1/admin/media",
                        files={"file": (name, io.BytesIO(await _png(color)), "image/png")},
                        data={"category": category})
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _content(auth, title: str, body: str = "", cover_id: int | None = None) -> dict:
    payload = {"type": "article", "status": "draft", "title": title, "body_md": body}
    if cover_id:
        payload["cover_asset_id"] = cover_id
    r = await auth.post("/api/v1/admin/contents", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_rename_changes_display_name_only(auth):
    a = await _upload(auth, "old-name.png")
    r = await auth.patch(f"/api/v1/admin/media/{a['id']}", json={"filename": "新名字.png"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["filename"] == "新名字.png"
    assert d["url"] == a["url"] and d["storage_key"] == a["storage_key"]   # 地址不变


async def test_rename_strips_path_and_rejects_blank(auth):
    a = await _upload(auth, "x.png", color=(1, 2, 3))
    # 带路径的文件名只取末段，避免出现 ../ 之类的东西
    d = (await auth.patch(f"/api/v1/admin/media/{a['id']}",
                          json={"filename": "../../etc/evil.png"})).json()["data"]
    assert d["filename"] == "evil.png"
    assert (await auth.patch(f"/api/v1/admin/media/{a['id']}", json={"filename": "   "})).status_code == 400


async def test_categorize_only_relabels(auth):
    """改分类不搬文件、不改 URL —— 正文里的老链接必须继续有效。"""
    from app.core.config import settings
    a = await _upload(auth, "relabel.png")
    c = await _content(auth, "引用素材", body=f"![x]({a['url']})")
    r = await auth.post("/api/v1/admin/media/categorize", json={"ids": [a["id"]], "category": "model"})
    assert r.status_code == 200 and r.json()["data"]["updated"] == 1
    items = (await auth.get("/api/v1/admin/media?category=model")).json()["data"]["items"]
    m = next(x for x in items if x["id"] == a["id"])
    assert m["storage_key"] == a["storage_key"] and m["url"] == a["url"]
    assert (settings.media_path / a["storage_key"]).exists()
    body = (await auth.get(f"/api/v1/admin/contents/{c['id']}")).json()["data"]["body_md"]
    assert body == f"![x]({a['url']})"


async def test_usage_groups_by_content(auth):
    """正文链接 / 封面 / 附件三处都算引用，自动归到对应文章下。"""
    a = await _upload(auth, "used.png", color=(200, 10, 10))
    b = await _upload(auth, "cover.png", color=(10, 200, 10))
    c = await _upload(auth, "free.png", color=(10, 10, 200))
    art = await _content(auth, "用了两张图", body=f"正文引用 ![x]({a['url']})", cover_id=b["id"])

    items = {x["id"]: x for x in (await auth.get("/api/v1/admin/media?page_size=50")).json()["data"]["items"]}
    assert [u["id"] for u in items[a["id"]]["used_by"]] == [art["id"]]
    assert [u["id"] for u in items[b["id"]]["used_by"]] == [art["id"]]
    assert items[c["id"]]["used_by"] == []

    # 右下拉：按内容分组 + 未被引用计数
    g = (await auth.get("/api/v1/admin/media/contents")).json()["data"]
    assert g["items"][0]["id"] == art["id"] and g["items"][0]["count"] == 2
    assert g["unused"] == 1 and g["total"] == 3

    # 按内容筛选
    only = (await auth.get(f"/api/v1/admin/media?content_id={art['id']}")).json()["data"]
    assert {x["id"] for x in only["items"]} == {a["id"], b["id"]}
    # 未被引用筛选
    unused = (await auth.get("/api/v1/admin/media?unused=1")).json()["data"]
    assert {x["id"] for x in unused["items"]} == {c["id"]}
    # 不存在的内容 → 空列表（不是全量）
    empty = (await auth.get("/api/v1/admin/media?content_id=999999")).json()["data"]
    assert empty["items"] == [] and empty["total"] == 0


async def test_delete_blocked_reports_titles(auth):
    a = await _upload(auth, "guarded.png", color=(50, 60, 70))
    await _content(auth, "保护它的文章", body=f"![x]({a['url']})")
    r = await auth.delete(f"/api/v1/admin/media/{a['id']}")
    assert r.status_code == 409
    data = r.json()["data"]
    assert data["contents"][0]["title"] == "保护它的文章"
    assert "保护它的文章" in r.json()["message"]
