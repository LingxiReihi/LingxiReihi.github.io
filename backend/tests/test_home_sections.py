"""首页新数据面：热门按 浏览/点赞/评论 加权排序；团队名片含 super、只发三字段。"""
from tests.test_public import seed_contents  # noqa: F401

TITLES = ("第一篇文章", "第二篇文章", "机械臂")


async def _bump(**kw):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import Comment, Content
    async with SessionLocal() as db:
        c = (await db.execute(select(Content).where(Content.title == kw.pop("title")))).scalar_one()
        for k, v in kw.items():
            setattr(c, k, v)
        for i in range(kw.get("comments", 0)):
            db.add(Comment(content_id=c.id, nickname=f"访客{i}", email=f"v{i}@example.com",
                           body="写得真好", status="approved"))
        await db.commit()


async def _add_user(username, *, nickname, role="staff", is_active=True):
    from app.core.db import SessionLocal
    from app.models import User
    async with SessionLocal() as db:
        db.add(User(username=username, password_hash="x", nickname=nickname, role=role,
                    is_active=is_active, signature=f"{nickname}的签名"))
        await db.commit()


async def test_hot_orders_by_weighted_score_and_excludes_drafts(client, auth):
    await seed_contents()
    await _bump(title="第一篇文章", view_count=100)          # 100
    await _bump(title="第二篇文章", likes=20)                 # 20 × 8 = 160
    await _bump(title="机械臂", view_count=1, comments=2)     # 1 + 2 × 12 = 25
    hot = (await client.get("/api/v1/home")).json()["data"]["hot"]
    assert [h["title"] for h in hot[:3]] == ["第二篇文章", "第一篇文章", "机械臂"]
    assert hot[2]["comment_count"] == 2
    assert [h["score"] for h in hot[:3]] == [160, 100, 25]   # 权重钉在测试里：1 / 8 / 12
    assert "草稿" not in [h["title"] for h in hot]


async def test_one_comment_outranks_eleven_views(client, auth):
    await seed_contents()
    await _bump(title="第一篇文章", view_count=11)            # 11
    await _bump(title="第二篇文章", comments=1)               # 12
    hot = (await client.get("/api/v1/home")).json()["data"]["hot"]
    assert [h["title"] for h in hot[:2]] == ["第二篇文章", "第一篇文章"]


async def test_latest_mixes_all_types_newest_first(client, auth):
    await seed_contents()
    latest = (await client.get("/api/v1/home")).json()["data"]["latest"]
    titles = [x["title"] for x in latest]
    assert "草稿" not in titles
    # 跨类型按发布时间倒序：又一条(最新 chat) 排在 第一篇文章 之前，且三种类型都能出现
    assert titles.index("又一条") < titles.index("第一篇文章")
    assert {"article", "model", "chat"} <= {x["type"] for x in latest}


async def test_team_lists_every_active_admin_with_three_fields(client, auth):
    await seed_contents()
    await _add_user("staff_a", nickname="甲")
    await _add_user("staff_off", nickname="已停用", is_active=False)
    team = (await client.get("/api/v1/home")).json()["data"]["team"]
    names = [m["nickname"] for m in team]
    assert names[0] == "Test"                       # super 在最前
    assert "甲" in names and "已停用" not in names
    for m in team:
        assert set(m) == {"nickname", "avatar", "signature"}
        assert "email" not in m and "username" not in m
