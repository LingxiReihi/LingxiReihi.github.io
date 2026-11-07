# personal-web

个人博客站：前台五栏目（落地主页 / 博客 / 模型[3D·渲染·动画] / 杂谈 / 个人主页）+ 管理后台（内容上传、站点设置、访问监控、SEO 面板）。

- 前端：**Vue 3 + Vite 8 + TypeScript + Pinia + vue-router + Naive UI（后台）+ Tailwind CSS 4（前台）+ vite-ssg 构建期预渲染**（百度收录合规）
- 后端：**Python 3.12+ / FastAPI + SQLAlchemy 2.0 async + SQLite(WAL) + Alembic + PyJWT + bcrypt**
- 部署：Docker Compose + Caddy（香港服务器基线，见 `deploy/`）

设计文档：`docs/frontend-design.md` · `docs/backend-architecture.md` · `docs/api-reference.md` · 部署手册 `docs/static-gh-pages.md` · 旧服务器部署 `docs/deployment.md` · 决策记录 `docs/adr/`

> 线上现在是**纯静态只读镜像**：GitHub Pages + Cloudflare。本地后端负责写作与导出快照，CI 离线构建发布。评论/点赞/浏览统计/后台在线上不可用，详见 [`docs/static-gh-pages.md`](docs/static-gh-pages.md)。

## 本地开发

```bash
# 0. 一键启动前后端（首次需先完成下面的依赖/数据库初始化）
#    自动跳过被占用的端口；Ctrl+C 同时停止
./dev.sh

# ── 手动启动（可选）──
# 1. 后端
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows；Linux/Mac 用 source .venv/bin/activate
cp .env.example .env                                                    # 修改 JWT_SECRET 等
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.cli seed          # 创建管理员 + 默认设置
.venv/Scripts/python scripts/seed_demo.py     # （可选）演示数据
.venv/Scripts/python -m uvicorn app.main:app --port 8000

# 2. 前端（另开终端）
cd frontend
npm install
npm run dev            # http://localhost:5173，/api /media 自动代理到 8000
                       # 后端不在 8000 时：DEV_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

测试：`cd backend && .venv/Scripts/python -m pytest`（28 项，含端到端冒烟）。
类型检查：`cd frontend && npx vue-tsc --noEmit`。

## 线上部署（纯静态 GitHub Pages）

```bash
# 后端在跑、内容已发布后
cd frontend
STATIC_API_BASE=http://127.0.0.1:8000/api/v1 \
STATIC_SITE_ORIGIN=https://www.lingxi-reihi.cn \
npm run export:static       # 刷新 static-data/
npm run build:static:ci     # 本地验证构建（无需后端）
npm run preview:static      # http://127.0.0.1:4173

git add frontend/static-data
git commit -m "content: 更新静态快照"
git push                    # Actions 自动发布到 Pages
```

完整流程、Cloudflare 配置、缓存与 100MB 限制见 [`docs/static-gh-pages.md`](docs/static-gh-pages.md)。

## 旧版：服务器预渲染构建

```bash
cd frontend
SSG_API_BASE=http://127.0.0.1:8000/api/v1 \
VITE_SITE_ORIGIN=https://your-domain.com \
npx vite-ssg build
```

要求后端在跑（构建期枚举 published 内容生成 `/blog/<slug>.html` 等真实 HTML；后端不可达即 fail-fast）。`scripts/rebuild-frontend.sh` 封装了上述流程 + releases 原子切换，供服务器本机重建流水线使用。

## 旧版：服务器部署（deploy/，当前线上不再使用）

> **完整手册见 [`docs/deployment.md`](docs/deployment.md)**：架构总览、Docker/systemd 两种部署方式、`.env` 全变量表、本机重建流水线、Caddy、百度 SEO、备份回滚、故障排查、安全检查清单。

快速四步（Docker 方案）：

1. 服务器 clone 仓库，安装 Node ≥ 20（本机重建需要）
2. `backend/.env`：`JWT_SECRET`（32 字节+）、`SITE_URL`、`ADMIN_USERNAME/PASSWORD`；配置 `REBUILD_SCRIPT` 指向 `scripts/rebuild-frontend.sh` 绝对路径（并导出 `SITE_ORIGIN` 环境变量）；日后取得百度推送 token 后填 `BAIDU_PUSH_API` + `SEO_PUSH_ENABLED=true`，在后台 SEO 面板批量补推待推 URL
3. 首次 `docker compose run --rm backend alembic upgrade head && docker compose run --rm backend python -m app.cli seed`；构建一次前端；`deploy/.env` 写入 `SITE_ORIGIN=https://your-domain.com` 后 `docker compose up -d`（域名写死在 `deploy/Caddyfile`，Caddy 自动签发/续期 Let's Encrypt）
4. 到百度搜索资源平台完成站点验证（`BAIDU_VERIFY_NAME/CONTENT` 配 env）并提交 `sitemap.txt`

## 目录

```
backend/   FastAPI 应用（app/{api,services,models,core,middleware,tasks}）
frontend/  Vue SSG 应用（src/{api,stores,router,layouts,views,components,composables}）
scripts/   运维脚本（rebuild-frontend.sh）
deploy/    Docker/Caddy 部署产物
docs/      设计文档 + ADR
spark-output/  设计链路上下文（Brief/Scope/Journey/Flow 产物，非运行时代码）
```
