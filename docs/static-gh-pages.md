# 纯静态发布（GitHub Pages + Cloudflare）

线上形态：本地后端写内容 → 导出静态快照 → GitHub Actions 构建 → Pages artifact 发布 → Cloudflare 只做 DNS/CDN。
线上没有后端进程，站点是只读镜像。

## 数据流

```
backend/data（SQLite + media）
        │  npm run export:static（本地，需后端）
        ▼
frontend/static-data/   site.json / search.json / content/*.json / media/ / feed.xml / sitemap.* / robots.txt
        │  提交到仓库
        ▼
GitHub Actions  npm run build:static:ci（无后端）
        │  vite-ssg 预渲染 + 拷 media/SEO + 404.html + .nojekyll + CNAME
        ▼
frontend/dist  → actions/upload-pages-artifact → actions/deploy-pages
        ▼
www.lingxi-reihi.cn（Cloudflare → GitHub Pages）
```

## 首次接入

1. 建 GitHub 仓库，把本目录提交到 `main`。`frontend/static-data/` 必须一并提交（CI 构建的唯一数据源）。
2. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**。
3. **Custom domain** 填 `www.lingxi-reihi.cn`，等待 GitHub 签发证书。
4. Cloudflare DNS：`www` 的 CNAME 指向 `<用户名>.github.io`。
   - 首次验证/签发证书建议先设为「仅 DNS」；证书就绪后再开橙色云朵。
   - SSL/TLS 模式必须是 **Full (strict)**，不要用 Flexible（会重定向循环）。
5. 推送 `main` 触发 `.github/workflows/deploy-pages.yml`。

## 日常发文

```bash
# 1. 起本地后端（读 backend/data）
cd backend
.venv/Scripts/python -m uvicorn app.main:app --port 8000

# 2. 另开终端起前端，进 /admin 写文章
cd frontend
npm run dev

# 3. 导出静态快照（后端不在 8000 时用 STATIC_API_BASE 指过去）
STATIC_API_BASE=http://127.0.0.1:8000/api/v1 \
STATIC_SITE_ORIGIN=https://www.lingxi-reihi.cn \
npm run export:static

# 4. 本地完整构建 + 预览（不需要后端）
npm run build:static:ci
npm run preview:static        # http://127.0.0.1:4173

# 5. 提交 static-data 与代码，push main → Actions 自动发布
```

`npm run build:static` = 导出 + 构建；`build:static:ci` = 只构建（CI 用）。

## 静态化后失效的能力

- 评论、点赞、浏览数、下载数、热门榜：前端已移除；相关接口不再打包。
- 后台 `/admin`：静态构建不生成页面、不打包 chunk；本地开发模式仍可用。
- 运行时搜索：改为 `search.json` 本地索引（标题/摘要/正文），语义是子串匹配。
- 访问统计、公告通知、忘记密码、媒体上传：仅本地后端可用。
- 内容筛选/分页/栏目/上下篇：全部在浏览器里基于 `site.json` 计算。

## 产物与路径

| 路径 | 内容 |
| --- | --- |
| `frontend/static-data/` | 唯一数据源（提交到仓库），约 27MB，媒体最大 4.6MB |
| `frontend/dist/data/site.json` | 站点配置 + 首页/关于 + 标签/栏目 + 三类列表 |
| `frontend/dist/data/content/` | 每篇详情（`post/`、`model/`、`chat/`） |
| `frontend/dist/data/search.json` | 本地搜索索引 |
| `frontend/dist/media/` | 从 `backend/data/media` 复制，URL 仍为 `/media/...` |
| `dist/<section>/<slug>/index.html` | `dirStyle: nested`，无扩展名可直接访问 |

## 缓存

- 构建时把 `static-data` 的版本号写进数据 URL（`?v=YYYYMMDDHHMMSS`），每次发布自动失效。
- HTML 与 `data/*.json` 建议 Cloudflare 短缓存（例如 5–10 分钟）；`assets/*` 与 `media/*` 文件名带哈希或内容不变，可长缓存。

## 限制与排障

- GitHub 单文件上限 **100MB**，Pages 站点 **1GB**，带宽软限制 **100GB/月**；不支持 Git LFS。导出脚本遇到 ≥100MB 文件会直接失败。
- `static-data/media` 随仓库增长；大模型文件建议压缩或外链，不要依赖 LFS。
- 页面 404：仓库根 `404.html` 使用 SPA 外壳，未知路径会跳到 `/404`。
- 构建报「找不到静态快照」：先跑 `npm run export:static`。
- 线上仍是旧内容：确认 `static-data` 已提交、Actions 成功，再检查 Cloudflare 缓存。
- 自定义域验证失败：把 Cloudflare 代理先关掉（仅 DNS），等 GitHub 证书签发后再开。