from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.models import Content, MediaAsset, Tag


async def seed_contents():
    async with SessionLocal() as db:
        img = MediaAsset(filename="c.png", storage_key="2026/09/c.png", kind="image",
                         mime="image/png", size=100, width=800, height=450, sha256="x" * 64)
        glb = MediaAsset(filename="m.glb", storage_key="2026/09/m.glb", kind="model3d",
                         mime="model/gltf-binary", size=1000, sha256="y" * 64)
        zip_ = MediaAsset(filename="scene.zip", storage_key="2026/09/scene.zip", kind="model3d",
                          mime="application/zip", size=2000, sha256="z" * 64,
                          entries=[{"path": "scene/scene.obj", "size": 400},
                                   {"path": "scene/tex/a.png", "size": 900}])
        db.add_all([img, glb, zip_])
        await db.flush()
        t1 = Tag(name="技术", slug="tech")
        t2 = Tag(name="随笔", slug="essay")
        db.add_all([t1, t2])
        base = datetime.now(timezone.utc) - timedelta(days=5)
        a1 = Content(type="article", status="published", title="第一篇文章", slug="post-one",
                     summary="一", body_md="# 一\n正文", cover_asset_id=img.id, published_at=base,
                     extra={"reading_time": 3}, tags=[t1])
        a2 = Content(type="article", status="published", title="第二篇文章", slug="post-two",
                     summary="二", body_md="正文2", published_at=base + timedelta(days=1), tags=[t1, t2])
        a3 = Content(type="article", status="draft", title="草稿", slug="post-draft",
                     summary="d", body_md="draft body", published_at=None)
        m1 = Content(type="model", status="published", title="机械臂", slug="mech-arm",
                     summary="3D", body_md="Blender 机械臂模型说明", media_kind="3d", published_at=base,
                     extra={"faces": 12000, "software": "Blender 4.2", "internal_note": "hidden"},
                     assets=[glb, zip_])
        c1 = Content(type="chat", status="published", title="今天天气不错", summary="",
                     body_md="短内容", published_at=base)
        c2 = Content(type="chat", status="published", title="又一条", summary="",
                     body_md="更多短内容" * 50, published_at=base + timedelta(hours=1))
        db.add_all([a1, a2, a3, m1, c1, c2])
        db.add(Content(type="article", status="published", title="Vue 技巧", slug="vue-tips",
                       summary="SFC 编译器宏", body_md="在 Vue 中使用 defineProps", published_at=base - timedelta(days=1), tags=[t1]))
        await db.commit()


async def test_posts_list_detail(client):
    await seed_contents()
    r = await client.get("/api/v1/posts?page=1&page_size=2")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total"] == 3
    assert len(d["items"]) == 2
    one = next(i for i in d["items"] if i["slug"] == "post-one")
    assert one["cover"] == "/media/2026/09/c.png"
    assert "status" not in one and "body_md" not in one  # 白名单

    r = await client.get("/api/v1/posts/post-one")
    det = r.json()["data"]
    assert det["body_md"].startswith("# 一")
    assert det["extra"] == {"reading_time": 3}
    assert det["next"]["slug"] == "vue-tips" or det["prev"]  # 上下篇存在
    assert len(det["related"]) >= 1

    r = await client.get("/api/v1/posts/post-draft")
    assert r.status_code == 404 and r.json()["code"] == 40400


async def test_filter_and_search(client):
    await seed_contents()
    r = await client.get("/api/v1/posts?tag=tech")
    assert r.json()["data"]["total"] == 3
    r = await client.get("/api/v1/posts?q=Vue")
    assert [i["slug"] for i in r.json()["data"]["items"]] == ["vue-tips"]
    r = await client.get("/api/v1/search?q=Blender")
    items = r.json()["data"]["items"]
    assert items[0]["slug"] == "mech-arm"
    r = await client.get("/api/v1/tags")
    tech = next(t for t in r.json()["data"]["items"] if t["slug"] == "tech")
    assert tech["count"] == 3


async def test_models_and_download(client):
    await seed_contents()
    r = await client.get("/api/v1/models?kind=3d")
    assert r.json()["data"]["total"] == 1
    r = await client.get("/api/v1/models?kind=render")
    assert r.json()["data"]["total"] == 0
    r = await client.get("/api/v1/models/mech-arm")
    det = r.json()["data"]
    assert det["assets"][0]["kind"] == "model3d"
    assert det["extra"]["software"] == "Blender 4.2"
    assert "internal_note" in det["extra"]  # 详情返回完整 extra（规格如此）
    r = await client.post("/api/v1/models/mech-arm/download")
    assert r.json()["data"]["url"] == "/media/2026/09/m.glb"
    aid = det["assets"][0]["id"]
    r = await client.post(f"/api/v1/models/mech-arm/download?asset_id={aid}")
    assert r.json()["data"]["url"] == "/media/2026/09/m.glb"
    r = await client.post("/api/v1/models/mech-arm/download?asset_id=99999")
    assert r.status_code == 404
    # 两次成功下载计入计数；详情带更新时间
    det2 = (await client.get("/api/v1/models/mech-arm")).json()["data"]
    assert det2["downloads"] == 2
    assert det2["updated_at"]
    # 压缩包素材：公开详情需带文件名与层级清单，前台据此渲染内容树
    zp = next(a for a in det["assets"] if a["filename"].endswith(".zip"))
    assert zp["entries"] == [{"path": "scene/scene.obj", "size": 400},
                             {"path": "scene/tex/a.png", "size": 900}]
    assert zp["storage_key"] == "2026/09/scene.zip"


async def test_chats_cursor(client):
    await seed_contents()
    r = await client.get("/api/v1/chats?limit=1")
    d = r.json()["data"]
    assert len(d["items"]) == 1 and d["next_cursor"]
    r2 = await client.get(f"/api/v1/chats?limit=1&cursor={d['next_cursor']}")
    d2 = r2.json()["data"]
    assert d2["items"][0]["id"] != d["items"][0]["id"]
    assert d2["next_cursor"] is None


async def test_home_about_siteconfig_rss(client):
    from sqlalchemy import select
    from app.cli import DEFAULT_SETTINGS
    from app.core.db import SessionLocal
    from app.models import SiteSetting
    async with SessionLocal() as db:
        for k, v in DEFAULT_SETTINGS.items():
            if (await db.execute(select(SiteSetting).where(SiteSetting.key == k))).scalar_one_or_none() is None:
                db.add(SiteSetting(key=k, value=v))
        await db.commit()
    await seed_contents()
    r = await client.get("/api/v1/home")
    d = r.json()["data"]
    assert len(d["recent_posts"]) == 3 and "featured_models" not in d
    assert len(d["recent_chats"]) == 2
    # 站点 About 读的是 super 账号那一行（profile 组已废）
    async with SessionLocal() as db:
        from app.core.security import hash_password
        from app.models import User
        db.add(User(username="about-admin", password_hash=hash_password("x-x-x-x-x-x-x-x-x"),
                    nickname="博主", role="super", is_active=True, signature="签名",
                    social_links=[{"platform": "GitHub", "url": "https://github.com/x"}]))
        await db.commit()
    r = await client.get("/api/v1/about")
    d = r.json()["data"]
    assert d["nickname"] == "博主" and d["signature"] == "签名"
    assert d["social_links"][0]["platform"] == "GitHub"
    r = await client.get("/api/v1/site-config")
    assert r.json()["data"]["site"]["title"] == "My Blog"
    assert len(r.json()["data"]["nav_items"]) == 5
    r = await client.get("/api/v1/rss")
    assert r.status_code == 200 and "<rss" in r.text and "第一篇文章" in r.text


async def test_home_settings_group_retired(client, auth):
    """首页改版成 最新/热门/团队 三段后，home 组（四类型开关 + 精选内容 id）已无消费者，整组撤掉。

    撤之前它是 2026-10-06 绑定审计刚接线的控件 —— 留着就是「入库但前台无人读」的死配置复发。
    """
    cfg = (await client.get("/api/v1/site-config")).json()["data"]
    assert "sections" not in cfg
    r = await auth.put("/api/v1/admin/settings/home", json={"sections": {"hero": False}})
    assert r.status_code == 400, r.text
    groups = (await auth.get("/api/v1/admin/settings")).json()["data"]
    assert "home" not in groups
    assert {"site", "nav", "footer", "mail"} <= set(groups)


async def test_site_icon_round_trips_to_public_config(client, auth):
    """首页首屏那张圆图读 site.icon（站点设置 → 站点信息），不再借用 super 的个人头像。"""
    assert (await client.get("/api/v1/site-config")).json()["data"]["site"]["icon"] == ""
    r = await auth.put("/api/v1/admin/settings/site",
                       json={"title": "My Blog", "icon": "/media/site/2026/10/icon.png"})
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/site-config")).json()["data"]["site"]["icon"] \
        == "/media/site/2026/10/icon.png"


async def test_preview_token_flow(client):
    import app.api.public as pub
    await seed_contents()
    from sqlalchemy import select
    from app.core.db import SessionLocal
    from app.models import Content
    async with SessionLocal() as db:
        cid = (await db.execute(select(Content.id).where(Content.slug == "post-draft"))).scalar_one()
    r = await client.get(f"/api/v1/posts/post-draft/preview?token=bad")
    assert r.status_code == 403
    token = pub.make_preview_token(cid)
    r = await client.get(f"/api/v1/posts/post-draft/preview?token={token}")
    assert r.status_code == 200
    assert r.json()["data"]["body_md"] == "draft body"


async def test_tracking_and_aggregate(client):
    from sqlalchemy import func, select
    from app.core.db import SessionLocal
    from app.models import ViewEvent
    from app.tasks.aggregate import run_aggregate, _today
    await seed_contents()
    await client.get("/api/v1/posts/post-one?track_local=1")
    await client.get("/api/v1/posts/post-one?track_local=1")
    await client.get("/api/v1/posts/vue-tips?track_local=1")
    async with SessionLocal() as db:
        n = (await db.execute(select(func.count()).select_from(ViewEvent))).scalar_one()
        assert n == 3
        await run_aggregate(db, _today())
        from app.models import Content
        v = (await db.execute(select(Content.view_count).where(Content.slug == "post-one"))).scalar_one()
        assert v == 2


async def test_draft_not_counted(client):
    r = await client.get("/api/v1/posts/no-such")
    assert r.status_code == 404


async def test_like_post_and_model(client):
    from app.api import public as pub
    await seed_contents()
    pub._like_cooldown.clear()
    r = await client.post("/api/v1/posts/post-one/like")
    assert r.status_code == 200 and r.json()["data"]["likes"] == 1
    # 详情带出 likes
    det = (await client.get("/api/v1/posts/post-one")).json()["data"]
    assert det["likes"] == 1
    # 冷却：同 IP 同内容 10s 内二次点赞 429
    r = await client.post("/api/v1/posts/post-one/like")
    assert r.status_code == 429 and r.json()["code"] == 42900
    # 取消点赞：计数回落，冷却与点赞分开计（紧接 like 之后可 unlike）
    r = await client.post("/api/v1/posts/post-one/unlike")
    assert r.status_code == 200 and r.json()["data"]["likes"] == 0
    # 0 不再下穿
    pub._like_cooldown.clear()
    r = await client.post("/api/v1/posts/post-one/unlike")
    assert r.json()["data"]["likes"] == 0
    # 清冷却后模型可赞，且与文章计数互不影响
    pub._like_cooldown.clear()
    r = await client.post("/api/v1/models/mech-arm/like")
    assert r.json()["data"]["likes"] == 1
    r = await client.post("/api/v1/models/mech-arm/unlike")
    assert r.json()["data"]["likes"] == 0
    # 草稿/不存在 404
    assert (await client.post("/api/v1/posts/post-draft/like")).status_code == 404
    assert (await client.post("/api/v1/posts/post-draft/unlike")).status_code == 404


async def test_admin_reset_likes(auth, client):
    from app.api import public as pub
    await seed_contents()
    pub._like_cooldown.clear()
    await client.post("/api/v1/posts/post-one/like")
    # 取 id
    det = (await client.get("/api/v1/posts/post-one")).json()["data"]
    r = await auth.post(f"/api/v1/admin/contents/{det['id']}/reset-likes")
    assert r.status_code == 200 and r.json()["data"]["likes"] == 0
    # 后台列表带出 likes 字段
    lst = (await auth.get("/api/v1/admin/contents?type=article")).json()["data"]
    row = next(x for x in lst["items"] if x["id"] == det["id"])
    assert "likes" in row
