"""Markdown 外链图片入库（F-3 扩展）：命名、改写、SSRF 与失败隔离。"""
import io

import httpx
import pytest
from PIL import Image

from app.core.errors import AppException
from app.services import image_import


def _png(color=(0, 128, 128), size=(120, 80)) -> bytes:
    im = Image.new("RGB", size, color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


async def _create(auth, body_md: str, slug: str = "astar-path"):
    r = await auth.post("/api/v1/admin/contents", json={
        "type": "article", "status": "draft", "title": "外链图测试",
        "slug": slug, "body_md": body_md})
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_import_rewrites_md_and_names_by_slug(auth, monkeypatch):
    """外链图下载入库，文件名 `slug-图片名`，正文地址改成本地 /media。"""
    png = _png()
    seen: list[str] = []

    async def fake_fetch(url, transport=None):
        seen.append(url)
        return png, "image/png"

    monkeypatch.setattr(image_import, "_fetch", fake_fetch)
    md = ("# 标题\n\n"
          "![封面](https://cdn.example.com/pics/Cover%20Art.png)\n\n"
          "![已本地](/media/blog/2026/11/abc.png)\n\n"
          "![data](data:image/png;base64,AAAA)\n")
    d = await _create(auth, md)
    r = await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images", json={"body_md": md})
    assert r.status_code == 200, r.text
    out = r.json()["data"]

    # 只抓了那一张外链图（站内路径与 data: 跳过）
    assert seen == ["https://cdn.example.com/pics/Cover%20Art.png"]
    assert len(out["imported"]) == 1 and not out["failed"]
    item = out["imported"][0]
    assert item["filename"] == "astar-path-Cover-Art.png"
    # 回写绝对地址：导出到站外也能取到图
    assert item["url"].startswith("https://example.com/media/blog/")
    assert out["body_md"].count(item["url"]) == 1
    assert "/media/blog/2026/11/abc.png" in out["body_md"]        # 本地相对地址原样保留
    assert "data:image/png" in out["body_md"]
    # 两张本地链接被识别出来并跳过，各带原因
    assert {s["src"]: s["reason"] for s in out["skipped"]} == {
        "/media/blog/2026/11/abc.png": "站内相对路径",
        "data:image/png;base64,AAAA": "内联数据",
    }
    assert out["total"] == 3

    # 素材确实进了库，且带缩略图
    r = await auth.get("/api/v1/admin/media?q=astar-path-Cover")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["thumb"]


async def test_import_keeps_title_and_alt(auth, monkeypatch):
    async def fake_fetch(url, transport=None):
        return _png(), "image/png"

    monkeypatch.setattr(image_import, "_fetch", fake_fetch)
    md = '![示意图](https://a.example.com/x/y.png "图注")'
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images",
                           json={"body_md": md})).json()["data"]
    assert out["body_md"].startswith("![示意图](https://example.com/media/")
    assert out["body_md"].endswith(' "图注")')


async def test_own_absolute_media_urls_are_skipped(auth, monkeypatch):
    """回写的是本站绝对地址：再次点击不能把自家图片当外链重下一遍。"""
    async def boom(url, transport=None):
        raise AssertionError(f"不该下载本站素材：{url}")

    monkeypatch.setattr(image_import, "_fetch", boom)
    md = ("![a](https://example.com/media/blog/2026/11/a.png)\n\n"
          "![b](https://www.example.com/media/blog/2026/11/b.png)\n\n"     # www 变体同样算本站
          "![c](/media/blog/2026/11/c.png)")
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images",
                           json={"body_md": md})).json()["data"]
    assert out["imported"] == [] and out["failed"] == []
    assert out["body_md"] == md
    assert len(out["skipped"]) == 3          # 两张本站绝对地址 + 一张相对路径


async def test_foreign_host_with_media_path_is_still_imported(auth, monkeypatch):
    """别的站点上的 /media 路径不是本站素材，照常下载。"""
    async def fake_fetch(url, transport=None):
        return _png(), "image/png"

    monkeypatch.setattr(image_import, "_fetch", fake_fetch)
    md = "![x](https://cdn.other.com/media/2026/11/x.png)"
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images",
                           json={"body_md": md})).json()["data"]
    assert len(out["imported"]) == 1
    assert out["imported"][0]["url"].startswith("https://example.com/media/blog/")


async def test_import_handles_angle_bracket_url(auth, monkeypatch):
    """Markdown 允许 <…> 包裹含空格的 URL，尖括号不能进文件名。"""
    async def fake_fetch(url, transport=None):
        assert url == "https://a.example.com/pics/my shot.png"
        return _png(), "image/png"

    monkeypatch.setattr(image_import, "_fetch", fake_fetch)
    md = "![带空格](<https://a.example.com/pics/my shot.png>)"
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images",
                           json={"body_md": md})).json()["data"]
    assert out["imported"][0]["filename"] == "astar-path-my-shot.png"
    assert out["body_md"] == f"![带空格]({out['imported'][0]['url']})"


async def test_import_failure_does_not_touch_md(auth, monkeypatch):
    """单张失败只记原因，正文保持原样，不中断其它张。"""
    async def fake_fetch(url, transport=None):
        if "bad" in url:
            raise AppException(41500, "不是图片（text/html）")
        return _png(), "image/png"

    monkeypatch.setattr(image_import, "_fetch", fake_fetch)
    md = "![ok](https://a.example.com/ok.png)\n\n![bad](https://a.example.com/bad.png)"
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images",
                           json={"body_md": md})).json()["data"]
    assert len(out["imported"]) == 1
    assert out["failed"][0]["src"].endswith("/bad.png")
    assert "https://a.example.com/bad.png" in out["body_md"]      # 失败的原样保留
    assert "/media/" in out["body_md"]


async def test_import_no_external_images(auth):
    md = "![本地](/media/blog/2026/11/x.png)"
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images",
                           json={"body_md": md})).json()["data"]
    assert out["imported"] == [] and out["failed"] == [] and out["body_md"] == md


async def test_import_uses_stored_body_when_omitted(auth, monkeypatch):
    async def fake_fetch(url, transport=None):
        return _png(), "image/png"

    monkeypatch.setattr(image_import, "_fetch", fake_fetch)
    md = "![x](https://a.example.com/stored.png)"
    d = await _create(auth, md)
    out = (await auth.post(f"/api/v1/admin/contents/{d['id']}/import-images", json={})).json()["data"]
    assert len(out["imported"]) == 1


async def _login_as(client, username: str, password: str = "staff-pass-123"):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"


async def test_import_requires_write_permission(auth, make_staff, client):
    d = await _create(auth, "![x](https://a.example.com/x.png)")
    await make_staff("writer", grants=[])          # 无任何授权
    await _login_as(client, "writer")
    r = await client.post(f"/api/v1/admin/contents/{d['id']}/import-images", json={})
    assert r.status_code == 403


async def test_import_rejects_other_owners_content(auth, make_staff, client):
    """归属隔离：他人内容不可代为抓图（会消耗其配额并改写其正文）。"""
    d = await _create(auth, "![x](https://a.example.com/x.png)")
    await make_staff("editor", grants=[{"permission": "content:write"},
                                       {"permission": "media:write"}])
    await _login_as(client, "editor")
    r = await client.post(f"/api/v1/admin/contents/{d['id']}/import-images", json={})
    assert r.status_code == 403


async def test_ssrf_blocks_private_addresses():
    for host in ("127.0.0.1", "localhost", "169.254.169.254", "10.0.0.5", "::1"):
        with pytest.raises(AppException):
            await image_import._assert_public(host)


async def test_fetch_rejects_non_image_and_oversize(monkeypatch):
    async def no_check(host):
        return None

    monkeypatch.setattr(image_import, "_assert_public", no_check)

    html = httpx.MockTransport(lambda req: httpx.Response(
        200, headers={"content-type": "text/html"}, content=b"<html>"))
    with pytest.raises(AppException):
        await image_import._fetch("https://a.example.com/page.html", html)

    big = httpx.MockTransport(lambda req: httpx.Response(
        200, headers={"content-type": "image/png"},
        content=b"\x89PNG" + b"\0" * (image_import.MAX_BYTES + 1)))
    with pytest.raises(AppException):
        await image_import._fetch("https://a.example.com/big.png", big)


async def test_fetch_follows_redirect_and_validates_each_hop(monkeypatch):
    async def no_check(host):
        return None

    monkeypatch.setattr(image_import, "_assert_public", no_check)
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if req.url.path == "/old.png":
            return httpx.Response(302, headers={"location": "/new.png"})
        return httpx.Response(200, headers={"content-type": "image/png"}, content=_png())

    data, ctype = await image_import._fetch("https://a.example.com/old.png",
                                            httpx.MockTransport(handler))
    assert ctype == "image/png" and data[:4] == b"\x89PNG"
    assert seen == ["https://a.example.com/old.png", "https://a.example.com/new.png"]


def test_local_link_detection(monkeypatch):
    """本地链接判定：本站任意路径、本机地址、相对路径、内联数据一律不下载。"""
    monkeypatch.setattr(image_import.settings, "site_url", "https://www.example.com")
    hosts = image_import.local_hosts()
    assert {"www.example.com", "example.com", "localhost", "127.0.0.1"} <= hosts

    local = {
        "/media/blog/2026/11/a.png": "站内相对路径",
        "images/a.png": "站内相对路径",
        "//cdn.other.com/a.png": "站内相对路径",
        "data:image/png;base64,AAA": "内联数据",
        "https://www.example.com/media/a.png": "本站地址",
        "https://example.com/avatars/00.svg": "本站地址",        # 本站非 /media 路径也算本地
        "http://localhost:5173/media/a.png": "本机地址",          # 公网 site_url 下的本机地址
        "http://127.0.0.1:8001/media/a.png": "本机地址",
    }
    for url, reason in local.items():
        assert image_import.local_reason(url, hosts) == reason, url
        assert image_import.is_external(url, hosts) is False, url

    for url in ("https://cdn.other.com/a.png", "https://cdn.other.com/media/a.png"):
        assert image_import.local_reason(url, hosts) == ""
        assert image_import.is_external(url, hosts) is True


def test_stem_ext_fallbacks():
    assert image_import._stem_ext("https://x.com/a/cover.png?w=800", "image/png") == ("cover", ".png")
    # 无扩展名：按 Content-Type 补
    assert image_import._stem_ext("https://x.com/img/12345", "image/jpeg") == ("12345", ".jpg")
    # 非图片扩展名：按 Content-Type 覆盖
    assert image_import._stem_ext("https://x.com/pic.php", "image/webp") == ("pic", ".webp")
    # 无文件名：兜底 img
    assert image_import._stem_ext("https://x.com/", "image/png") == ("img", ".png")
    # 只取末段，路径穿越片段与危险字符都不会进文件名
    stem = image_import._stem_ext("https://x.com/../../etc/pass%3Cwd", "image/png")[0]
    assert stem == "pass-wd" and "/" not in stem and "." not in stem
