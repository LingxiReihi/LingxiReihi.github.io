"""栏目计数两档口径：count=本级直属，total=含全部子孙（前台目录栏徽章用后者）。"""
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.models import Column, Content


async def seed_tree():
    """编程基础 ▸ C# ▸ WPF：父 0 篇直属、子 2 篇（另 1 篇草稿）、孙 4 篇。"""
    async with SessionLocal() as db:
        base = datetime.now(timezone.utc) - timedelta(days=3)
        parent = Column(name="编程基础", slug="basics", type="article")
        db.add(parent)
        await db.flush()
        child = Column(name="C#", slug="csharp", type="article", parent_id=parent.id)
        db.add(child)
        await db.flush()
        grand = Column(name="WPF", slug="wpf", type="article", parent_id=child.id)
        db.add(grand)
        await db.flush()
        n = 0
        for col, direct in ((parent, 0), (child, 2), (grand, 4)):
            for _ in range(direct):
                n += 1
                db.add(Content(type="article", status="published", title=f"c{n}", slug=f"c{n}",
                               body_md="x", published_at=base, column_id=col.id))
        db.add(Content(type="article", status="draft", title="d", slug="d", body_md="x",
                       published_at=None, column_id=child.id))
        await db.commit()


async def _columns(client):
    r = await client.get("/api/v1/columns", params={"type": "article"})
    assert r.status_code == 200
    return {i["slug"]: i for i in r.json()["data"]["items"]}


async def test_parent_count_stays_direct_but_total_includes_descendants(client):
    await seed_tree()
    cols = await _columns(client)
    # 夹具自己先钉住：上一版把 db.add 漏了、parent_id 全是 NULL，树退化成平铺，
    # 表现为「total 少算」这种看不出根因的失败
    assert cols["csharp"]["parent_id"] == cols["basics"]["id"]
    assert cols["wpf"]["parent_id"] == cols["csharp"]["id"]
    assert cols["basics"]["count"] == 0          # 本级语义不动：后台删除确认文案依赖它
    assert cols["basics"]["total"] == 6          # 自身 0 + C# 2 + WPF 4
    assert cols["csharp"]["count"] == 2
    assert cols["csharp"]["total"] == 6          # 孙层只被算一次，不重复累加
    assert cols["wpf"]["count"] == 4 and cols["wpf"]["total"] == 4


async def test_leaf_total_equals_column_filter_result(client):
    """徽章数字必须等于点进去后的列表总数 —— 筛选本来就含子孙，两处口径不能分家。"""
    await seed_tree()
    for slug, expected in (("basics", 6), ("csharp", 6), ("wpf", 4)):
        cols = await _columns(client)
        assert cols[slug]["total"] == expected
        r = await client.get("/api/v1/posts", params={"column": slug})
        assert r.json()["data"]["total"] == expected, slug
