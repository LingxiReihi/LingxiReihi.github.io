# personal-web 服务器部署手册（前端 + 后端）

> 目标读者：第一次把本站部署到服务器（推荐香港 VPS，Debian 12 / Ubuntu 22.04+）的你。
> 部署模型：**后端常驻 + 前端构建期预渲染（vite-ssg）+ Caddy 统一入口**，发布内容后由后端触发**服务器本机重建**流水线自动刷新静态页（决策背景见 `docs/adr/0001-ssg.md`）。

---

## 1. 架构总览

```
浏览器
  │  https://你的域名 (80 → 443 自动跳转 + 自动 TLS 证书)
  ▼
┌────────────────────────── Caddy（deploy/Caddyfile）──────────────────────────┐
│  /api/*  /media/*  /sitemap.xml  /sitemap.txt  /robots.txt                    │
│  /feed.xml  /baidu_verify_*            ──► reverse_proxy ──► backend:8000     │
│  其余（页面/静态资源）          ──► file_server ◄── /srv/site = frontend/dist  │
│                                        （vite-ssg 预渲染产物，符号链接原子切换）│
└───────────────────────────────────────────────────────────────────────────────┘
                                              │
                          FastAPI + SQLAlchemy(async) + SQLite(WAL)
                          data/app.db · data/media/<类别>/YYYY/MM/uuid.ext
                                              │
                              发布/改状态 → 触发 REBUILD_SCRIPT（本机重建）
                              重建成功 → 百度主动推送（未配置 token 则记 pending_push）
```

要点：
- **前台页面是静态 HTML**（每个已发布内容一个 `/blog/<slug>.html`），百度爬虫拿到的是完整渲染后的正文；后台 `/admin/*` 是纯 SPA，不参与预渲染。
- **图片等素材由后端直出** `/media/…`（生产也可让 Caddy 直接读盘，见 §5）。
- 数据库是单文件 SQLite（WAL 模式），个人站量级无需独立数据库服务。

## 2. 服务器要求

| 项 | 要求 | 说明 |
|---|---|---|
| CPU/内存 | ≥1 vCPU / **≥1 GB 可用内存**（推荐 2 GB） | `vite-ssg build` 在 Node 里跑渲染，<1 GB 容易 OOM；缓解见 §10 |
| 磁盘 | ≥10 GB | 代码 + Node_modules + releases（保留 3 份）+ 素材 |
| OS | Debian 12 / Ubuntu 22.04+ | 其他发行版自行调整包管理命令 |
| Node.js | **≥ 20**（推荐 22 LTS） | 裸机部署（§3-B/§4-A）或 Docker+宿主 cron（§4-C）需要；纯 Docker 构建（§4-D）宿主机免装，用 NodeSource 或 nvm 安装 |
| Python | 3.12+（推荐 3.12/3.13） | 后端运行时；Docker 方案则随镜像 |
| Docker + Compose v2 | 可选 | 走 §3-A 容器方案时必需 |
| 域名 + DNS | A 记录指向服务器 IP | Caddy 自动签发 Let's Encrypt 证书的前提 |
| 防火墙端口 | 放行 80/TCP、443/TCP、**443/UDP**（22 自限来源） | 8000 **不要**对公网开放。443/UDP 给 Caddyfile 里开的 HTTP/3（`protocols h1 h2 h3`）；不放行也不会出错，浏览器自动回落 H2。云主机（如阿里云）的放行规则在**控制台安全组**里，不在这块盘上，重装系统不影响它 |

```bash
# Debian/Ubuntu 快速准备（Node 22 + Docker）
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs git
curl -fsSL https://get.docker.com | sudo bash
sudo systemctl enable --now docker
```

## 3. 后端部署

推荐目录布局（下文 `$APP_DIR` = `~/personal-web`）：

```
~/personal-web/
├── backend/    frontend/    scripts/    deploy/    docs/
```

```bash
git clone <你的仓库地址> ~/personal-web && cd ~/personal-web
```

### 3-A. 方式一：Docker Compose（推荐，含 Caddy）

1. 写 `backend/.env`（全量变量见 §3-C 表格，最小可用集）。**Docker 模式不要配置 `REBUILD_SCRIPT`**——后端跑在容器里，容器内没有仓库脚本/Node/前端源码，配置了只会让重建任务报 `exit=127 not found`；重建改由宿主机承担：装了 Node 走 §4-C，不想装 Node 走 §4-D（纯 Docker 构建）：
   ```bash
   JWT_SECRET=$(openssl rand -hex 32)
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD='一个强密码'
   SITE_URL=https://你的域名
   CORS_ORIGINS=https://你的域名
   ```
   ```bash
   chmod 600 backend/.env
   ```
2. 建数据目录并写 `deploy/.env`：**必须在任何 `docker compose` 命令之前完成**。`docker-compose.yml` 的 `builder` 服务用了 `${SITE_ORIGIN:?...}`，Compose 在执行任何子命令（包括 `run` / `stop` / `logs`）前都会对整个文件做变量插值，缺这个变量会直接报：
   `error while interpolating services.builder.environment.SITE_ORIGIN: required variable SITE_ORIGIN is missing`
   `deploy/.env` 被 `.gitignore` 忽略，新克隆的仓库里没有，需要手工建：
   ```bash
   mkdir -p backend/data/media
   printf 'SITE_ORIGIN=https://你的域名\n' > deploy/.env
   chmod 600 deploy/.env
   ```
3. 首次初始化（容器内跑一次即可，之后 compose 会自动 `alembic upgrade head`）。`admin` 不在 docker 组时一律加 `sudo -n`：
   ```bash
   cd deploy
   sudo -n docker compose run --rm backend alembic upgrade head
   sudo -n docker compose run --rm backend python -m app.cli seed   # 创建管理员+默认设置
   ```
   > 也可以跳过 `run alembic`，直接 `sudo -n docker compose up -d backend`：镜像 CMD 已经包含 `alembic upgrade head && uvicorn ...`，启动时自动迁移。
4. 前端产物先手动构建一次（§4-B），然后拉起（域名直接写在 `Caddyfile`，见 §5；builder/compose 共用的 `SITE_ORIGIN` 放 `deploy/.env`）：
   ```bash
   cd ~/personal-web/deploy
   sudo -n docker compose up -d
   ```
   `docker-compose.yml` 说明：backend 仅映射 `127.0.0.1:8000`（供宿主机重建脚本调用，不对公网）；`data/` 挂卷持久化；caddy 挂载的是**整个 frontend 目录**到 `/srv/site`（Caddyfile root 指向 `/srv/site/dist`）——因为 `dist` 是重建脚本原子替换的符号链接，若直接挂 `dist`，Docker 会在容器创建时把链接解析定死，之后切换新版本容器仍服务旧目录；挂父目录后容器内按请求实时解析链接，切换即时生效、无需重启 caddy。
5. 验证：`curl -s https://你的域名/api/v1/health` 应返回 `{"code":0,...}`；浏览器打开首页。

### 3-B. 方式二：裸机 systemd + uvicorn（不装 Docker）

```bash
cd ~/personal-web/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && $EDITOR .env          # 按 §3-C 填好
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli seed              # 输出管理员密码（未设 env 时随机生成一次）
mkdir -p data/media
```

systemd 单元 `/etc/systemd/system/pw-api.service`：

```ini
[Unit]
Description=personal-web API
After=network.target

[Service]
User=你的用户
WorkingDirectory=/home/你的用户/personal-web/backend
EnvironmentFile=/home/你的用户/personal-web/backend/.env
# SITE_ORIGIN 供重建脚本子进程使用（与 SITE_URL 同值）
Environment=SITE_ORIGIN=https://你的域名
ExecStart=/home/你的用户/personal-web/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now pw-api
journalctl -u pw-api -f          # 看日志
```

> 裸机模式下 Caddy 用官方包安装，配置见 §5；`proxy 127.0.0.1:8000` 替代 compose 里的 `backend:8000`。
> ⚠️ `--workers 1` 是有意为之：重建流水线（**后端进程内**的构建锁 + 合并窗口）是进程内状态，多 worker 会各跑一份、并发构建互踩。跨进程/跨容器的那道互斥是 `rebuild-frontend.sh` 里的 `flock` 文件锁，见 §4-D，两者不是一回事、缺一不可。

### 3-C. 环境变量全表（`backend/.env`）

| 变量 | 默认 | 生产建议 | 说明 |
|---|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | 保持 | 相对路径基于 backend 工作目录 |
| `JWT_SECRET` | dev 占位 | **必填**，`openssl rand -hex 32` | 泄露=可伪造管理员登录；**它同时是邮件 API Key 的加密主密钥来源（HKDF 派生），改动后库里旧密文解不开，要到「站点设置 → 邮件通道」重填一次** |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | admin / 随机打印一次 | 首次 seed 用 | 仅 seed 时读取；改密码走后台界面 |
| `MEDIA_ROOT` | `./data/media` | 保持 | 素材落盘目录（分类子目录自动创建） |
| `CORS_ORIGINS` | `http://localhost:5173` | `https://你的域名`（逗号分隔多个） | 前后端同域反代时其实用不到，留作 API 直连场景 |
| `SITE_URL` | `http://localhost:5173` | `https://你的域名` | 生成 sitemap/RSS/推送 URL 的基址 |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | 120 / 7 | 默认 | 登录态时长 |
| `REBUILD_SCRIPT` | 空 | **仅裸机模式填** rebuild 脚本绝对路径；Docker 模式留空（§4-C/D/E） | 空=发布后跳过重建（记 skipped），前台靠 cron 重建更新 |
| `REBUILD_REQUEST_FILE` | 空 | **Docker 模式填** `/app/data/.rebuild-request`（§4-E watcher） | 后端发布时写请求文件，宿主机 watcher 拉起构建 |
| `REBUILD_MERGE_SECONDS` | 10 | 默认 | 合并窗口：窗口内多次发布只构建一次 |
| `BAIDU_PUSH_API` | 空 | 拿到 token 后填 | 形如 `https://data.zz.baidu.com/urls?site=xxx&token=xxx` |
| `SEO_PUSH_ENABLED` | false | 有 token 后 true | 推送总开关 |
| `BAIDU_VERIFY_NAME` / `BAIDU_VERIFY_CONTENT` | 空 | 百度验证文件参数 | 后端直出 `/baidu_verify_*.html`，见 §7 |
| `MAIL_API_URL` | `http://mail:8000/api/external/send` | **容器内网默认值即可用**（mail 与 backend 同在 `deploy_default` 网络） | 「忘记密码」发信端点；本地开发在容器网络外，需填公网 `https://mail.lingxi-reihi.cn/api/external/send` |
| `MAIL_API_KEY` | 空 | **建议留空**，改在后台「站点设置 → 邮件通道」填 | 仅作兜底；界面填的值密文入库，优先于这里 |
| `MAIL_OVERRIDE_TO` | 空 | **线上留空** | 非空时所有重置邮件改投该地址（只用于排障，每次改写都落 warning 日志） |

（`REBUILD_INTERNAL_TOKEN` 为回调方案预留，本机重建模式不需要。）

**邮件通道的前置条件**：Key 必须人工去 `https://mail.lingxi-reihi.cn` 登录（OTP）→ 设置页「外部接入 API」生成，明文只显示一次；没生成时对该端点的调用返回 `403 EXTERNAL_DISABLED`，本站按"发信失败"处理（**不改口令**）。本节功能引入新的运行时依赖 `cryptography`（见 `backend/requirements.txt`），上线时必须 `docker compose build backend`，仅 `up -d` 换镜像不会装上新包。

**发信队列的兜底冲刷（待用户同意后才加）**：评论通知与审核通知都先进 `mail_queue`，入队时会顺带冲一次；没有新事件时积压要靠一条 cron：

```
15 * * * * cd /home/admin/personal-web && sudo -n docker compose -f deploy/docker-compose.yml exec -T backend python -m app.cli mail-drain >> /home/admin/pw-mail-drain.log 2>&1
```

放 `15` 分是为了避开 `0 4` 的前端整点重建与 `*/5` 的 watcher。排障用 `python -m app.cli mail-status`（打印各状态计数、退避暂停到几点、最近一条错误）。

## 4. 前端部署（vite-ssg 预渲染）

### 4-A. 本机重建流水线（推荐，发布即自动更新）

> 适用 §3-B 裸机部署（后端进程与仓库同机同文件系统）。**Docker 模式请看 §4-C（宿主跑脚本）或 §4-D（纯 Docker 构建）**——容器内没有脚本与 Node，发布自动触发不可用。

`scripts/rebuild-frontend.sh` 已由后端在内容发布/改状态时自动调用（`REBUILD_SCRIPT` 配置后）。它做的事：

1. `cd $APP_DIR/frontend`；`SITE_ORIGIN`、`SSG_API_BASE`（默认本机后端）取自环境变量；
2. 无 `node_modules` 时自动 `npm ci`；
3. `SSG_OUT_DIR=releases/<时间戳>.tmp npx vite-ssg build` —— 构建期**调用本机后端 API 枚举已发布内容**生成路由；后端不可达或无 published 内容会 fail-fast（退出非 0，不会切版本）；
4. 产物目录改名去 `.tmp` → `ln -sfn` 原子切换 `dist` 符号链接 → 只保留最近 3 个 release。

服务器需要一次性准备：

```bash
cd ~/personal-web/frontend && npm ci --no-audit --no-fund
# 确保 uvicorn 服务进程环境里可见 SITE_ORIGIN（systemd 见 §3-B；compose 可在 env_file 加一行）
```

注意：
- 重建以**运行后端的同一用户**执行，需对该仓库 frontend 目录有写权限。
- 每次构建约 30–90 秒；期间旧版本继续服务，切换瞬时完成。
- 手动触发：后台 SEO 面板「立即重建」，或 `SITE_ORIGIN=https://你的域名 bash scripts/rebuild-frontend.sh`。

### 4-B. 手动构建（首次部署 / 排障）

```bash
cd ~/personal-web/frontend
npm ci --no-audit --no-fund
SSG_API_BASE=http://127.0.0.1:8000/api/v1 \
VITE_SITE_ORIGIN=https://你的域名 \
npx vite-ssg build
ln -sfn "$PWD/dist" ~/personal-web/frontend/dist_static_check   # 可选：确认产物
```
产物在 `frontend/dist/`（`blog/xxx.html` 平铺结构，dirStyle=flat）。Docker 方案里 caddy 挂载整个 frontend 目录后按 `/srv/site/dist` 引用它。

### 4-C. Docker 模式的重建调度（宿主机 cron）

容器内没有 Node/仓库源码，重建必须在**宿主机**跑。一次性准备：

```bash
cd /home/admin/personal-web
chmod +x scripts/rebuild-frontend.sh
cd frontend && npm ci --no-audit --no-fund
```

`crontab -e`（以 admin 用户）追加——每天凌晨 4 点重建一次（构建约 30–90 秒，串行、原子切换，风险低。频率演进：每小时 → 2026-09-24 每 4 小时 → 2026-10-15 每天一次）：

```cron
0 4 * * * APP_DIR=/home/admin/personal-web SITE_ORIGIN=https://你的域名 SSG_API_BASE=http://127.0.0.1:8000/api/v1 bash /home/admin/personal-web/scripts/rebuild-frontend.sh >> /home/admin/pw-rebuild.log 2>&1
```

这里的「4 点」是**系统时区**的 4 点。宿主 `/etc/timezone` 是 `Asia/Shanghai`，所以就是东八区凌晨 4 点。**别写 `CRON_TZ=`**：本站宿主机一直是 vixie-cron 血统（Ubuntu 24.04 时代是 `cron 3.0pl1-184ubuntu2`，2026-10-19 重装 Debian 12 后是 `cron 3.0pl1-162`），`/usr/sbin/cron` 二进制里搜不到该字符串——**两个系统上都带阳性对照验过**：同一搜法下 `SHELL` / `HOME` / `PATH` / `LOGNAME` 各命中 1，而 `CRON_TZ` 与 `TZ` 均为 0（`CRON_TZ` 是 cronie 的特性）。写了只是给任务塞一个没人读的环境变量——看着像钉住了时区，实际什么都没做。代价是时区依赖系统设置：将来换机若系统时区变成 UTC，这一行会静默漂到中午 12 点，届时改 `/etc/timezone` 或把调度写成 `0 20 * * *`（UTC 20:00 = 东八区 04:00）。**重装/新建机器后先跑一次 `timedatectl` 确认时区**，这一行才不会悄悄漂。

配套行为：
- `.env` 不配 `REBUILD_SCRIPT` → 后台发布时重建任务记 **skipped**（这是预期，不是故障），URL 照常进入推送队列；前台最迟次日凌晨 4 点更新。
- 急于上新一篇时手动触发：`sudo systemctl run` 不必——直接执行上面 cron 那行命令即可，或到后台「SEO 面板 → 立即重建」（注意：Docker 模式该按钮同样会因容器无脚本而失败，勿用）。
- 若希望发布即重建（无 cron 延迟），请改用 §3-B 裸机 systemd 部署，`REBUILD_SCRIPT` 直连本机脚本才有效。

### 4-D. 纯 Docker 构建（宿主机不装 Node）

§4-C 的重建脚本仍需宿主机有 Node ≥ 20。若不想在宿主机装 Node，用 compose 里的一次性 `builder` 服务（`node:22-bookworm-slim`）在容器内构建，产物 `releases/` 与 `dist` 符号链接通过挂载落回宿主 `frontend/`，caddy 即时可见。

**前提**：`deploy/docker-compose.yml` 已内置 `builder` 服务（`profiles: ["build"]`，平时不启动）。它把整个仓库挂到 `/repo`、`node_modules` 用命名卷持久化、经 compose 内网 `http://backend:8000` 枚举内容。

一次性构建（首次会在卷内跑 `npm ci`，约 1–2 分钟）：

```bash
cd /home/admin/personal-web/deploy
SITE_ORIGIN=https://你的域名 docker compose --profile build run --rm builder \
  bash /repo/scripts/rebuild-frontend.sh
```

看到 `rebuild ok: releases/<时间戳>` 即成功；验证：`curl -s https://你的域名/ | grep -o '<title>[^<]*'`。

定时重建（宿主机 crontab -e，admin 用户，无需 Node）：

```cron
0 4 * * * cd /home/admin/personal-web/deploy && SITE_ORIGIN=https://你的域名 docker compose --profile build run --rm builder bash /repo/scripts/rebuild-frontend.sh >> /home/admin/pw-rebuild.log 2>&1
```

注意事项：
- `SITE_ORIGIN` 必须通过环境变量传入（compose 里 `${SITE_ORIGIN:?}` 缺失即报错），值与 `backend/.env` 的 `SITE_URL` 一致。
- 后端需已在跑（`docker compose ps` 确认 backend healthy/up）；`run` 会自动拉起依赖的 backend，但首次后端可能还没就绪导致枚举失败——失败再跑一次即可。
- `package.json` / `package-lock.json` 变更后**容器内会自动重装**：`rebuild-frontend.sh` 比对 lock 的 sha256 前 16 位与卷内 `node_modules/.pw-lock-sha` 指纹，不一致就 `npm ci` 并重新盖章（旧版只探测 `.bin/vite-ssg`，被「卷里装过一批旧依赖」骗过，2026-10-06 连撞 32 次）。要彻底重来才 `docker volume rm deploy_node_modules`。
- 容器以 root 构建，`frontend/releases/*` 与 `dist` 在宿主上属 root；caddy 能读，无碍。若之后想手动在宿主跑脚本需 `sudo` 或改属主。
- **构建互斥锁**：`rebuild-frontend.sh` 开头对 `$APP_DIR/backend/data/.rebuild.lock` 取 `flock -n`，拿不到就 **exit 3**。锁放这里而不是放 watcher，是因为两条路径都要覆盖——宿主 cron 直接跑脚本、watcher 在 builder 容器里跑，而容器内 `/repo` 就是宿主 `$APP_DIR` 的 bind mount，两边看到的是同一个 inode。于是「04:00 定时重建」与「watcher 触发的构建」不会再并发把 1.6GB 内存的机器压到 OOM（2026-09 真宕过十几分钟）。**退出码必须非零**：watcher 靠它决定删不删请求文件，把「被跳过」报成成功就等于那次内容永远不重建。
- **builder 的 npm 缓存是持久卷 `npm_cache`（挂到容器 `/root/.npm`）**：builder 每次都是新建容器，冷缓存要从 registry 重下 290+ 个包。2026-10-19 依赖变更时一次构建因此超过 watcher 的 5 分钟间隔 → cron 自己叠自己 → 三个 `npm ci` 共用 `node_modules` 卷互相删树（`tarball seems corrupted`），并发下载把单包拖到 380–635 秒后 `ETIMEDOUT`，卷被清空、请求文件永远消费不掉。挂上缓存后同一件 `npm ci` 实测 10 秒、整轮 watcher 构建 27 秒。
- ~~后台「SEO 面板 → 立即重建」在本模式下不可用~~ **watcher 模式（推荐）下可用**，见下。

### 4-E. Watcher 模式：Docker 下「发布即自动重建」

§4-D 的 cron 是无脑定时全量重建；若你希望**发布/改动内容后自动触发**（含后台「手动重建」按钮），用请求文件 + watcher：

1. `backend/.env` 加一行（容器内路径，落在与宿主共享的 `data/` 卷）：
   ```
   REBUILD_REQUEST_FILE=/app/data/.rebuild-request
   ```
   然后 `docker compose up -d --force-recreate backend`。此后每次发布，后端把待重建 URL 写入该文件，重建任务记 `requested`。
2. 宿主机 crontab 改为每 5 分钟轮询 watcher（替代 §4-D 的整点定时行）：
   ```cron
   */5 * * * * APP_DIR=/home/admin/personal-web SITE_ORIGIN=https://你的域名 bash /home/admin/personal-web/scripts/rebuild-watcher.sh >> /home/admin/pw-watcher.log 2>&1
   ```
   `scripts/rebuild-watcher.sh` 逻辑：无请求文件→静默退出；有→拉起 builder 构建，**成功才清除请求**（失败保留，下轮自动重试）。被 §4-D 那把 flock 挡住时也必须是非零退出 → 请求保留、下一轮重试，绝不能把「被跳过」报成「构建完成」，否则那次内容永远不会被重建。2026-10-19 正反例都实测过：持锁跑 watcher 得到 `rebuild skipped: 另一个构建正持有 /repo/backend/data/.rebuild.lock` + 退出码 1 + 请求文件仍在、`dist` 未动；放锁后同一链路 27 秒构建成功并消费请求。
3. 效果：发布 → ≤5 分钟前台更新；SEO 面板「手动重建」按钮同样走此链路；面板「前端重建」卡显示「Watcher 模式（自动）」。

## 5. Caddy 配置

`deploy/Caddyfile` 写死域名、共三个站块（不再用 `{$SITE_ADDRESS}` 变量）：

```caddy
lingxi-reihi.cn { redir https://www.lingxi-reihi.cn{uri} permanent }   # 裸域走 TLS 后 301 到 www
http://47.82.123.169 { redir https://www.lingxi-reihi.cn{uri} permanent } # IP 无法签发证书，仅 HTTP 301
www.lingxi-reihi.cn {          # 规范主机，自动 HTTPS
  @api path /api/*  → reverse_proxy backend:8000   # 全部 JSON API
  @media path /media/* → reverse_proxy backend:8000 # 素材直出（含缩略图）
  /sitemap.xml /sitemap.txt /robots.txt /feed.xml(重写→/api/v1/rss) /baidu_verify_* → 后端
  handle { root * /srv/site/dist; try_files {path} {path}.html {path}/index.html {path} /index.html; file_server }
}
```

- 主机名不带 `http://` 前缀即触发 Caddy 自动 HTTPS：向 Let's Encrypt 签发证书、**到期前 30 天自动续期**、80 自动 308 跳 443——无需任何额外 cron；证书存 `caddy_data` 卷，容器重建不丢。
- matcher 用具名 `@xxx path ...` 展开写法：`handle /path { 单行 }` 内联块不被 Caddyfile 解析器接受（caddy validate 报 "Unexpected next token after '{'"）。
- `try_files` 回退链适配 vite-ssg 平铺产物：`/blog/hello` → `/blog/hello.html`；兜底 `/index.html`（SPA 客户端路由接管 404）。
- `/assets/*` 一年强缓存（文件名带 hash）；`index.html` `no-store` 保证发布后立即可见新版。
- 换域名：三个站块 + `backend/.env`（SITE_URL/SITE_ORIGIN/CORS_ORIGINS）+ `deploy/.env` + 两条 cron 的 SITE_ORIGIN 一起改，然后重建前端（canonical 是构建期烤进的）。
- 裸机部署时把 `backend:8000` 改成 `127.0.0.1:8000`，`/srv/site/dist` 换成 `~/personal-web/frontend/dist` 绝对路径。

## 6. 发布 → 重建 → 推送 时序

```
后台点「发布」 → 后端写库 → 触发重建任务：
  ① 合并窗口 10s（期间多次发布合并为一次构建）
  ② 跑 REBUILD_SCRIPT：成功→失效 sitemap 缓存→（若配置）百度推送；失败→记录 job 日志不影响内容
     REBUILD_SCRIPT 未配置 → job 记 skipped，前台不会更新！URL 仍进 pending_push
```
排查入口：后台 SEO 面板的重建任务列表（状态/日志尾部）与推送日志。

## 7. SEO 上线步骤（百度）

1. 百度搜索资源平台 → 添加站点 → 验证方式选「HTML 文件」，拿到形如 `baidu_verify_codeva-XXXX.html` 的文件名与内容；
2. `backend/.env` 填 `BAIDU_VERIFY_NAME` / `BAIDU_VERIFY_CONTENT` 并重启后端 → `curl https://域名/<验证文件名>` 应返回验证内容；
3. 提交 sitemap：平台「普通收录 - sitemap 提交」填 `https://你的域名/sitemap.txt`；
4. 拿到推送 token 后填 `BAIDU_PUSH_API` + `SEO_PUSH_ENABLED=true`，到后台 SEO 面板把 `pending_push` 队列批量补推。

## 8. 备份与恢复

**备份范围**（Docker 模式下逐项都不可再生，缺哪一项就永久失去哪一项）：

| 内容 | 位置 | 为什么必须在备份里 |
|---|---|---|
| 库 + 素材 | `backend/data/app.db`（+ `-wal`/`-shm`）、`backend/data/media/` | 内容、用户、评论、公告、统计、上传图片 |
| 配置三枚 | `backend/.env`、`deploy/.env`、`~/personal-mail/secrets/qq-secret.txt` | 全在 `.gitignore` 里，仓库没有。`JWT_SECRET` 换了＝所有人被登出 |
| personal-mail 卷 | `personal-mail_pm-data` | 里面的 **`master.key`** 丢了，已镜像的正文永久解不开，授权码也拿不回 |
| lexi 词书站（同机第三套） | `~/Dictionary/backend/data/`（`lexi.db` + `-wal` + **`.admin-password`**）、`~/Dictionary/backend/.env` | 主库文件只有 4 KB、2.5 MB 数据全在未合并的 `-wal` 里，**直接 tar 主库会备到一个空库**；`.admin-password` 丢了没人能登进词书站后台；`.env` 含 `JWT_SECRET`/`MAIL_API_KEY`，不在 git 里。代码本身在 `github.com:LingxiReihi/Dictionary` |
| caddy 两卷 | `deploy_caddy_data` / `deploy_caddy_config` | Let's Encrypt 证书 + ACME 账户密钥；不带就得重签，而 LE 每注册域每周限 5 张 |
| SSH | `~/.ssh/{id_ed25519,authorized_keys}` | 私钥没了新机 pull 不动代码，`authorized_keys` 没了你自己登不进 |
| 运维快照 | `crontab -l` 原文、`apt-mark showmanual`、`/etc/sysctl.d/99-swappiness.conf`、`swapon --show`、两仓库 `git bundle` | 重装后照单恢复，不用凭记忆猜 |

`node_modules` / `.venv` / 旧 `releases` / docker 镜像都不必备份，装回来即可。

### 8-A 每日备份

脚本就在仓库里：**`scripts/pw-backup.sh`**（与 `rebuild-frontend.sh` 同级，跟着 clone 走，重装机器 pull 回来就有）。装法：

```bash
mkdir -p ~/pw-backups && chmod 700 ~/pw-backups    # 产物目录，属主必须是跑备份的用户
```
```cron
30 3 * * * bash /home/admin/personal-web/scripts/pw-backup.sh >> /home/admin/pw-backup.log 2>&1
```

> 为什么用 `bash <路径>` 而不是给它加执行位：仓库是在 Windows 上维护的，`chmod +x` 不会落进 git（存的是 644）。真在服务器上补了执行位，`git status` 就会一直显示这个文件被改（改的是 mode 不是内容），而 `git checkout` 又会把 644 盖回来。用 `bash` 调用与另外三行 cron 同形，执行位这件事根本不参与。产物目录 `~/pw-backups` 必须 700、包必须 600（脚本自己会 chmod）。

它做什么（`bash -x` 逐步可核，别照抄改）：

1. 先确认 `backend` 容器在跑，否则直接失败退出——**绝不 tar 正在写的 `app.db-wal`**（旧机 WAL 里压着 4MB 未合并数据）；宿主机没有 `sqlite3 CLI`，所以三枚库（主站 / personal-mail / lexi）都借各自容器里的 python 走 **`sqlite3.Connection.backup()`** 取一致快照（服务不停、cron 不动）。lexi 是独立项目，**容器没在跑时只记一行 warn 跳过它**，不让别的停机把主站备份拖成失败。
2. 三枚快照都过 `PRAGMA integrity_check`，**不过就非零退出、不产出当天备份**（宁可缺一天，也不能备一个开不了的库）
3. 再打三个卷（`personal-mail_pm-data`、`deploy_caddy_data`、`deploy_caddy_config`）——`master.key` 与 LE 证书/ACME 账户密钥只在卷里
4. `crontab -l` 原文也进包（它不在任何卷里，重装即丢）
5. 产物 `~/pw-backups/pw-<日期>.tar.gz`（权限 600），同时留 `.list` 成员清单与 `.sha256` 校验和，默认保留 14 天（`PW_BACKUP_KEEP_DAYS` 可改；目录用 `PW_BACKUP_DIR`）
6. 备份内容与 `backend/.env`、`deploy/.env`、`qq-secret.txt`、SSH 私钥同级敏感 → **产物目录必须 700、包必须 600**，别再往里面加"公开可下载"的分享链接

**要清楚它防什么**：备份和原库在同一块盘上，防的是误删、库损坏、发布出事；**不防磁盘或实例丢失**——那靠云快照（§8-B 第 1 条）。要防后者就把 `pw-*.tar.gz` 再 scp/rclone 一份到异地，注意异地那份同样含明文密钥，得先加密。

> 历史备注：`/usr/local/bin/pw-backup.sh` + `/var/backups/pw` 是本文档改版前的写法，**线上从来没装过**（旧机 crontab 只有三行）。2026-10-19 重装后按上面这套装上并实跑验证过。

### 8-B 换系统盘 / 整机迁移（2026-10-19 由 Ubuntu 24.04 重装为 Debian 12，实跑顺序）

1. **先打云快照**（它是唯一回滚依据），**再把备份拉到本地**（异地一份）。单盘实例「更换操作系统」＝全盘初始化，机器上的任何副本都会一起消失。
2. SQLite 一律用 backup API 取快照（服务不用停、cron 不用动），别 `tar` 正在写的 `-wal`。
3. 记下 `sha256sum` → 传输 → 本地 `sha256sum -c` → 用 `PRAGMA integrity_check` **加表计数**（内容数 / 用户数 / 评论数）复验。**校验不过就别开始重装**。
4. 敏感那包（`.env`、私钥、卷 tar、库快照）单独 `openssl enc -aes-256-cbc -pbkdf2 -iter 600000` 加密，口令单独存；注意**云快照本身是全盘明文**，加密只防本机外泄。
5. 新机装齐：`timedatectl set-timezone`（§4-C 那条 cron 靠它）、2G `/swapfile` + `vm.swappiness=10` 并写 `/etc/fstab`、Docker CE 官方源、Node 22（NodeSource；Debian 自带版本不够）。
6. **启动顺序硬约束：先起 `deploy` 再起 `personal-mail`** —— 后者的 compose 把网络声明成 `external: deploy_default`，`deploy` 没起来网络就不存在，容器直接起不来。
7. 卷恢复：`docker volume create <项目前缀>_<名>`（例如 `deploy_caddy_data`、`personal-mail_pm-data`），再把 `volumes.tar` 解到 `/var/lib/docker/volumes`。**替换卷里的 `app.db` 时必须同时删掉旧 `-wal`/`-shm`**，否则新库配旧 WAL 语义不明。
8. `dist` 是符号链接：`ln -sfn releases/<时间戳> dist`。把当前那份 release 一起搬过去就能立刻出页，不必先赌一次构建（1.6 GB 内存跑 vite-ssg 有 OOM 风险）。
9. 重装后第一次登不进去是常态：`authorized_keys` 随盘没了。用控制台（VNC / Workbench 或「发送命令」云助手，后者免 SSH 免密码）以 root 建用户 + 回填公钥 + 写 `/etc/sudoers.d/`，之后 agent/脚本才能接管。
10. **动了 `package.json`/lock 就必须先 `npm ci` 再重建**（§4-C 的守卫按 lock 指纹判，别绕）。
11. 重启一次做收口验证：`docker.service` enabled、三容器自动回来、`crontab -l` 条数对、`swapon --show` 有值，再 `curl` 首页/`/api/v1/health`/子域名。

**恢复后必查的一项**：`releases/<当前>/blog/*.html` 的体积与 `<title>`。2026-10-19 迁移时发现旧机 10-18 那次 04:00 nightly 产物只有 ~5 KB、标题回落成通用的「文章 · …」——即**发布的是未预渲染空壳**，而同代码同命令手工重建是 ~240 KB 且标题为文章名。夜间构建期取数失败会静默退化成这种壳（构建仍 exit 0），所以别只看 `rebuild ok`。

## 9. 升级与回滚

**升级**：
```bash
cd ~/personal-web && git pull
cd backend && .venv/bin/pip install -r requirements.txt && .venv/bin/alembic upgrade head
sudo systemctl restart pw-api        # 或 docker compose up -d --build backend
bash scripts/rebuild-frontend.sh     # 拉取新模板/代码后重建前台（平时发布会自动做）
```
> ⚠️ 含数据库迁移的版本务必先跑 §8 手动备份一次。

**回滚前端版本**（重建出问题时秒级）：
```bash
cd ~/personal-web/frontend
ls -1t releases/                       # 找上一个好版本
ln -sfn releases/<时间戳> dist.tmp && mv dist.tmp dist
```
**回滚代码**：`git checkout <tag/commit>` 后重复升级步骤；alembic 可用 `alembic downgrade -1`（个别迁移不支持降级的以备份恢复为准）。

## 10. 故障排查

| 症状 | 常见原因 | 处理 |
|---|---|---|
| `error while interpolating services.builder.environment.SITE_ORIGIN: required variable SITE_ORIGIN is missing` | `deploy/.env` 不存在（新克隆仓库没有；被 `.gitignore` 忽略）。Compose 解析整个文件，任何子命令（`run`/`stop`/`logs`）都会先做插值 | 在 `deploy/` 下创建：`printf 'SITE_ORIGIN=https://你的域名\n' > deploy/.env && chmod 600 deploy/.env` |
| `docker: permission denied` | `admin` 不在 docker 组（设计如此） | 所有 compose 命令加 `sudo -n`，例如 `sudo -n docker compose ...` |
| 首页 502 / 无内容 | 后端没起来 | `journalctl -u pw-api` 或 `docker compose logs backend` |
| 发布后前台不更新 | `REBUILD_SCRIPT` 未配置（job 显示 skipped）或脚本失败 | 配 env；看 SEO 面板 job 日志尾部 |
| 重建 job `exit=127 …rebuild-frontend.sh: not found` | **Docker 模式**后端在容器里执行脚本，而容器内没有仓库脚本/Node（宿主机路径存在也没用） | 清空 `.env` 的 `REBUILD_SCRIPT`，改按 §4-C（宿主 Node）或 §4-D（纯 Docker builder）重建；`docker compose up -d backend` 生效 |
| builder 构建报 `ERR_MODULE_NOT_FOUND`（@tailwindcss/vite 等）/ npx 提示下载 vite-ssg | `node_modules` 命名卷是空的但脚本误判已装（旧版守卫 `[ -d node_modules ]` 对空卷目录恒真；已改为探测 `node_modules/.bin/vite-ssg`） | `git pull` 后重跑；或手动补一次：`docker compose --profile build run --rm builder npm ci --no-audit --no-fund` |
| 构建被杀 / OOM | 内存 <1 GB | 加 2 GB swap：`fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`；或减小并发（构建本就串行）；极端时手动 `NODE_OPTIONS=--max-old-space-size=512 npx vite-ssg build` |
| 构建 fail-fast「后端不可达」 | 重建时后端没跑 / `SSG_API_BASE` 指错 | 先起后端；检查脚本环境变量 |
| 端口 8000 被占（win 10048 同理 Linux EADDRINUSE） | 旧进程未退 | `ss -lntp \| grep 8000` 找到并停掉 |
| 图片 404 | `MEDIA_ROOT` 路径不对 / compose 卷没挂 | 确认 `backend/data/media` 存在且有文件；检查挂载 |
| 登录提示 401/token 过期 | 换了 `JWT_SECRET` 未重登（预期行为） | 重新登录即可 |
| 验证文件 404 | `BAIDU_VERIFY_*` 未填或未重启 | 填 env + 重启后端 |
| https 证书申请失败 | 域名未解析 / 80 被占 / 运营商封 25? 不影响但确认 80/443 可达 | 修 DNS 后 `docker compose restart caddy` 看日志 |

## 11. 安全检查清单

- [ ] `JWT_SECRET` 为随机 32+ 字节（非默认占位）
- [ ] 管理员密码已改掉 seed 默认/随机值（后台「修改密码」）
- [ ] `backend/.env` 权限 600，且未提交进 git（`.gitignore` 已含 `.env`）
- [ ] 8000 端口不对公网暴露（compose 仅 expose；裸机 uvicorn 绑 127.0.0.1）
- [ ] 防火墙/安全组仅放行 22/80/443
- [ ] 备份脚本在跑且有异地副本；做过一次恢复演练
- [ ] 评论/点赞已有蜜罐+IP 冷却，但仍建议定期看后台待审队列（先审后显默认安全）

---

附：本地开发方式（无需以上任何内容）见根目录 `README.md`；API 细节 `docs/api-reference.md`；后端内部设计 `docs/backend-architecture.md`。
