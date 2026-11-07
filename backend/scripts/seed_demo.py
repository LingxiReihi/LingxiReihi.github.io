"""演示数据 seed（幂等按 slug 判重）：python scripts/seed_demo.py
生成文章×3、模型×2（render/animation 各 1，含 3D 用极简 glb）、杂谈×5、封面图与 profile 设置。"""
import asyncio
import io
import json
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models import Content, MediaAsset, SiteSetting, Tag  # noqa: E402
from sqlalchemy import select  # noqa: E402

NOW = datetime.now(timezone.utc)


def make_png(color: str, w=1200, h=675) -> bytes:
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def make_glb() -> bytes:
    """12 字节头 + 空 JSON chunk 的最小合法 glTF 二进制。"""
    json_chunk = json.dumps({"asset": {"version": "2.0"}, "scenes": [{}], "scene": 0}).encode()
    json_chunk += b" " * (-len(json_chunk) % 4)
    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_chunk))
    chunk_header = struct.pack("<I4s", len(json_chunk), b"JSON")
    return header + chunk_header + json_chunk


import hashlib  # noqa: E402


async def add_asset(db, name: str, data: bytes, kind: str, mime: str,
                    width=None, height=None) -> MediaAsset:
    sha = hashlib.sha256(data).hexdigest()
    exist = (await db.execute(select(MediaAsset).where(MediaAsset.sha256 == sha))).scalar_one_or_none()
    if exist:
        return exist
    rel = f"{NOW:%Y/%m}/{sha[:12]}.{name.split('.')[-1]}"
    path = Path(settings.media_root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    a = MediaAsset(filename=name, storage_key=rel, kind=kind, mime=mime, size=len(data),
                   width=width, height=height, sha256=sha)
    db.add(a)
    await db.flush()
    return a


ARTICLE1 = """# 为什么我从 React 回到 Vue

用了一年的 React 18，最终还是把个人站迁回了 **Vue 3**。

## 响应式模型：心智负担的差异

`ref/reactive` 编译期解包 vs `useState` 闭包陷阱——

```python
count = 1
count += 1  # 对比 JS 闭包陷阱，Python 直觉一致
```

## 模板 vs JSX

模板的静态分析是真实的优化来源，不是语法口味问题。

## 结论

工具服务于心智模型，个人项目尤其如此。
"""

ARTICLE2 = """# Blender 布线笔记

 subdivision 工作流下保持四边面是大工程的前提。

## 常见反模式

- N-gon 直接细分
- 三角面藏在曲率大的地方

| 场景 | 建议 |
|---|---|
| 硬表面 | bevel + weighted normal |
| 角色 | quad toplogy only |
"""

ARTICLE3 = """# 静态站与百度收录的兼容之路

纯 SPA 对国内爬虫不友好，vite-ssg 构建期预渲染是个人站的最优解。

## 关键三点

1. HTML 首屏含正文
2. slug 发布后不变
3. sitemap 带 lastmod
"""


async def main() -> None:
    async with SessionLocal() as db:
        async def ensure_model(slug: str, **kw) -> Content | None:
            if (await db.execute(select(Content).where(Content.slug == slug))).scalar_one_or_none():
                return None
            c = Content(slug=slug, **kw)
            db.add(c)
            return c

        t_tech = (await db.execute(select(Tag).where(Tag.name == "技术", Tag.type == "article"))).scalar_one_or_none() or Tag(name="技术", slug="tech", type="article")
        t_bl = (await db.execute(select(Tag).where(Tag.name == "Blender", Tag.type == "article"))).scalar_one_or_none() or Tag(name="Blender", slug="blender", type="article")
        t_th = (await db.execute(select(Tag).where(Tag.name == "思考", Tag.type == "article"))).scalar_one_or_none() or Tag(name="思考", slug="thought", type="article")
        db.add_all([t_tech, t_bl, t_th])
        await db.flush()

        covers = {
            "vue": await add_asset(db, "vue.png", make_png("#39c5bb"), "image", "image/png", 1200, 675),
            "blender": await add_asset(db, "blender.png", make_png("#1f2c47"), "image", "image/png", 1200, 675),
            "seo": await add_asset(db, "seo.png", make_png("#0b1220"), "image", "image/png", 1200, 675),
            "render": await add_asset(db, "render.png", make_png("#5ee0d6", 900, 1200), "image", "image/png", 900, 1200),
            "glb": await add_asset(db, "demo.glb", make_glb(), "model3d", "model/gltf-binary"),
        }

        a1 = await ensure_model("vue-to-react-back-vue", type="article", status="published",
                                title="为什么我从 React 回到 Vue", summary="响应式模型的心智负担差异，模板的静态分析价值。",
                                body_md=ARTICLE1, cover_asset_id=covers["vue"].id,
                                published_at=NOW - timedelta(days=3),
                                tags=[t_tech, t_th], extra={"reading_time": 6})
        a2 = await ensure_model("blender-topology", type="article", status="published",
                                title="Blender 布线笔记", summary="subdivision 工作流下保持四边面的实践清单。",
                                body_md=ARTICLE2, cover_asset_id=covers["blender"].id,
                                published_at=NOW - timedelta(days=1),
                                tags=[t_bl], extra={"reading_time": 4})
        a3 = await ensure_model("baidu-ssg-seo", type="article", status="published",
                                title="静态站与百度收录的兼容之路", summary="vite-ssg 预渲染 + sitemap + 主动推送实践。",
                                body_md=ARTICLE3, cover_asset_id=covers["seo"].id,
                                published_at=NOW - timedelta(hours=6),
                                tags=[t_tech], extra={"reading_time": 5})

        m1 = await ensure_model("sci-fi-corridor-render", type="model", status="published",
                                title="科幻走廊 · 场景渲染", summary="Blender 4.2 Cycles 场景练习，冷光源走廊。",
                                body_md="## 制作说明\n\nCycles + volumetric，霓虹洗墙灯。",
                                media_kind="render", cover_asset_id=covers["render"].id,
                                published_at=NOW - timedelta(days=2), assets=[covers["render"]],
                                extra={"software": "Blender 4.2", "faces": 184000, "materials": 12})
        m2 = await ensure_model("demo-cube-glb", type="model", status="published",
                                title="交互演示立方体", summary="Web 端可旋转的 glb 演示资产。",
                                body_md="拖拽旋转、滚轮缩放。", media_kind="3d",
                                cover_asset_id=covers["vue"].id, published_at=NOW - timedelta(days=4),
                                assets=[covers["glb"]],
                                extra={"software": "Blender 4.2", "faces": 12,
                                       "links": [{"label": "ArtStation", "url": "https://artstation.com"}]})

        chats = [
            ("今日份的渲染收敛了，Light map 采样 2048 足够。", NOW - timedelta(hours=2)),
            ("高铁上把 Vue Router 4.6 的变更扫了一遍，scrollBehavior 有惊喜。", NOW - timedelta(days=1)),
            ("楼下的桂花开了，秋天真的来了。写不动代码就出门走走。", NOW - timedelta(days=2)),
            ("N-gon 一时爽，subdivision 火葬场。教训。", NOW - timedelta(days=5)),
            ("把博客后台的自动保存从 60s 调到 30s，灵感消失的速度比我想象快。", NOW - timedelta(days=7)),
        ]
        for text, when in chats:
            if (await db.execute(select(Content).where(Content.type == "chat", Content.title == text[:40]))).scalar_one_or_none():
                continue
            db.add(Content(type="chat", status="published", title=text[:40], body_md=text,
                           summary=text[:60], published_at=when))

        # profile 设置
        profile = {
            "nickname": "Yimu",
            "signature": "写代码，也做 3D —— 一个工程师的个人角落",
            "bio_md": "白天写 **Python / TypeScript**，晚上泡在 Blender 里。\n\n这里记录技术思考、渲染习作和一些生活碎片。",
            "social_links": [
                {"platform": "GitHub", "url": "https://github.com/yimu"},
                {"platform": "Email", "url": "mailto:hi@example.com"},
                {"platform": "Bilibili", "url": "https://bilibili.com"},
            ],
            "skills": [
                {"group": "前端", "items": ["Vue 3", "TypeScript", "Vite", "Tailwind CSS"]},
                {"group": "后端", "items": ["Python", "FastAPI", "SQLAlchemy", "PostgreSQL"]},
                {"group": "创作", "items": ["Blender", "Cycles", "Geometry Nodes"]},
            ],
            "experience": [
                {"kind": "work", "title": "软件工程师", "org": "某科技公司", "start": "2022-07", "end": None,
                 "desc": "数据平台与 Web 全栈。"},
                {"kind": "edu", "title": "计算机科学与技术", "org": "某大学", "start": "2018-09", "end": "2022-06", "desc": ""},
            ],
        }
        extra_settings = {
            "site.description": "Yimu 的个人博客：技术文章、Blender 作品与生活杂谈。",
        }
        for k, v in {**{f"profile.{kk}": vv for kk, vv in profile.items()}, **extra_settings}.items():
            row = (await db.execute(select(SiteSetting).where(SiteSetting.key == k))).scalar_one_or_none()
            if row:
                row.value = v
            else:
                db.add(SiteSetting(key=k, value=v))
        await db.commit()
        print("seed_demo done: articles=3 models=2 chats=5 profile updated")


asyncio.run(main())
