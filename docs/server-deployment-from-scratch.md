# Debian 12 服务器从零部署手册

**适用项目：personal-web（主站）· personal-mail（发信中转）· Dictionary / Lexi（词书站）**

> 文档版本：2026-11-07
> 同源说明：本文件在三个仓库的 `docs/server-deployment-from-scratch.md` 各存一份，**内容逐字相同**。修改时改一份后用 `cp` 覆盖另外两份，三处一起提交，避免长期漂移。
> 本文命令均以线上用户 `admin`、应用目录 `/home/admin/...` 为例；换用户名或路径时整篇替换。

---

## 0. 先读这一页

### 0.1 这套部署最终长什么样

| 服务 | 线上入口 | 容器 / 项目 | 运行方式 | 数据落点 | 更新方式 |
|---|---|---|---|---|---|
| personal-web | `https://www.lingxi-reihi.cn` | `deploy-backend-1` + `deploy-caddy-1`，compose 项目 `deploy` | FastAPI 容器常驻 + 宿主机 Node 预渲染（vite-ssg） | `~/personal-web/backend/data`（SQLite + media + logs） | 后端重建镜像；前端重建 `releases/` 并原子切换 `dist` 符号链接 |
| personal-mail | `https://mail.lingxi-reihi.cn` | `personal-mail`，compose 项目 `personal-mail` | 多阶段镜像：Node 构建前端 → Python 运行，容器内 8000 | 命名卷 `personal-mail_pm-data`（`/data`） | `docker compose up -d --build` |
| Dictionary / Lexi | `https://learn.lingxi-reihi.cn` | `lexi-api`，compose 项目 `lexi` | 前端产物打进镜像，后端直出静态 + `/api/v1`，容器内 8010 | `~/Dictionary/backend/data/lexi.db`（WAL） | 宿主机 `npm run build` → `docker compose up -d --build` |

三套服务共用**同一个 Caddy**（80/443 只能有一个进程监听）。Caddyfile 存在 personal-web 仓库，mail 与 learn 的站点块也在里面。

### 0.2 硬件与系统基线（2026-11-07 线上实测）

| 项 | 实测值 | 说明 |
|---|---|---|
| OS | Debian 12.15 bookworm | 由阿里云控制台「更换操作系统」重装；内核 `6.1.0-33-amd64` |
| 内存 | 1676 MB，swap 2047 MB | 1.6G 小机，swap 必配；`vm.swappiness=10` |
| CPU / 磁盘 | 1 vCPU / 40 GB 单盘 | 无独立数据盘，换系统=全盘初始化 |
| Docker | 29.9.1，Compose v5.6.0 | docker.com 官方源 |
| Node / npm | 22.23.3 / 10.9.9 | NodeSource；Debian 自带的 18 不够 vite-ssg 用 |
| git | 2.39.5 | Debian 仓库版 |
| 防火墙 | 无 `ufw` | 放行规则在**阿里云安全组**，重装系统不影响 |
| 时区 | `Asia/Shanghai` | 04:00 定时重建依赖它 |

### 0.3 三个必须记住的硬约束

1. **网络有创建顺序**：`personal-web` 的 compose 声明 `lexi_net` 为 `external`；`personal-mail` 的 compose 声明 `deploy_default` 为 `external`。从零部署时先手工 `docker network create lexi_net`，再起 personal-web（它会创建 `deploy_default`），最后起 mail / lexi。
2. **同机只允许一个前端构建**：`rebuild-frontend.sh` 用 `backend/data/.rebuild.lock` 做 `flock`。手动重建避开每天 04:00（宿主 cron）前后几分钟；撞车在 1.6G 内存上会把机器压到 SSH 失联。
3. **卷里放的是不可再生数据**：`personal-mail_pm-data` 里的 `master.key`、`deploy_caddy_data` 里的 Let's Encrypt 证书与 ACME 账户密钥。**任何情况下都不要 `docker volume prune`。**

---

## 1. 架构与网络拓扑

```
公网 :80/:443（Caddy：自动 TLS + 80→443；HTTP/3 走 UDP 443）
  │
  ├─ www.lingxi-reihi.cn
  │    ├─ /api/*  /media/*  /sitemap.*  /robots.txt  /feed.xml  /baidu_verify_*
  │    │        └──► backend:8000（deploy-backend-1）
  │    └─ 其余   └──► /srv/site/dist（宿主 ~/personal-web/frontend/dist 符号链接）
  │
  ├─ lingxi-reihi.cn        ──► 301 到 https://www.lingxi-reihi.cn
  ├─ http://47.82.123.169   ──► 301 到 https://www.lingxi-reihi.cn（IP 签不了证书，只走 HTTP）
  ├─ mail.lingxi-reihi.cn   ──► mail:8000（personal-mail）
  └─ learn.lingxi-reihi.cn  ──► lexi-api:8010
```

### 1.1 Docker 网络

| 网络 | 谁创建 | 谁加入 | 用途 |
|---|---|---|---|
| `deploy_default` | personal-web compose（目录名 `deploy`） | `deploy-backend-1`、`deploy-caddy-1`、`personal-mail`（别名 `mail`） | Caddy 反代 backend / mail |
| `lexi_net` | Dictionary compose（`name: lexi`）或手工创建 | `lexi-api`、`deploy-caddy-1`、`deploy-backend-1`、`personal-mail` | Caddy 反代 lexi；backend / lexi 访问 `mail:8000` |

容器名与端口：

| 容器 | 宿主端口 | 说明 |
|---|---|---|
| `deploy-caddy-1` | `0.0.0.0:80`、`0.0.0.0:443`（TCP+UDP） | 唯一公网入口 |
| `deploy-backend-1` | `127.0.0.1:8000` | 只给宿主重建脚本和本机调试 |
| `lexi-api` | `127.0.0.1:8010` | 只给本机调试，公网走 Caddy |
| `personal-mail` | 不发布宿主端口 | 只在内网被 Caddy / backend / lexi 访问 |

### 1.2 启动顺序（从零）

```text
① sudo -n docker network create lexi_net
② personal-web: sudo -n docker compose up -d backend    ← 创建 deploy_default
③ personal-mail: sudo -n docker compose up -d --build   ← 需要 deploy_default + lexi_net
④ personal-web: sudo -n docker compose up -d caddy
⑤ Dictionary: sudo -n docker compose up -d --build      ← 需要 lexi_net
```

顺序 ②③④ 的严格部分只有网络依赖。Caddy 先启动也不会因 `mail` / `lexi-api` 不存在而配置失败（上游按请求解析），只是这两个域名在容器起来前会 502。

---

## 2. 准备清单

部署前把这些东西准备好，后面每一步都依赖它们：

- [ ] 阿里云实例：≥1 vCPU / 2 GB 内存 / 40 GB 盘，Debian 12。本文实测机器为 1.6 GB，靠 2 GB swap 撑住构建。
- [ ] **云快照**：重装/换系统盘前先打快照，这是唯一回滚依据。
- [ ] DNS A 记录（阿里云 DNS 或任意服务商）：
  - `@` → 服务器 IP（裸域 301 也要证书）
  - `www` → 服务器 IP
  - `mail` → 服务器 IP
  - `learn` → 服务器 IP
- [ ] 阿里云安全组放行：
  - `22/tcp`（来源限制为自己的出口 IP）
  - `80/tcp`、`443/tcp`（全网）
  - `443/udp`（可选；给 HTTP/3，未放行会自动回落 H2）
  - **不要**放行 8000 / 8010。
- [ ] 本机 SSH 公钥（用于登录 `admin`）。
- [ ] 三个 GitHub 仓库的读权限（`personal-web`、`personal-mail`、`Dictionary`）。
- [ ] 一个密码管理器；`JWT_SECRET`、管理员口令、QQ 授权码、迁移口令都只放那里。
- [ ] Let's Encrypt 限额意识：证书存在 `deploy_caddy_data` 卷里，正常续期不会重签；清卷/换机不带证书卷才会重新申请，可能撞每周限额。

---

## 3. 安装系统与创建登录用户

### 3.1 阿里云控制台重装

1. 先给实例打快照。
2. 「更换操作系统」→ Debian 12（bookworm）→ 重置 root 密码。
3. 用控制台的 VNC / Workbench（或「发送命令」云助手）以 root 登录。**重装后 `authorized_keys` 随系统盘消失，SSH 一定登不进去，这是正常现象。**
4. 本地清掉旧 host key：

```bash
ssh-keygen -R 47.82.123.169
```

### 3.2 在控制台以 root 建用户

```bash
apt-get update
apt-get install -y sudo curl ca-certificates

adduser --disabled-password --gecos "" admin
usermod -aG sudo admin

install -d -m 700 -o admin -g admin /home/admin/.ssh
printf '%s\n' 'ssh-ed25519 AAAA...你的公钥... you@example' \
  > /home/admin/.ssh/authorized_keys
chown admin:admin /home/admin/.ssh/authorized_keys
chmod 600 /home/admin/.ssh/authorized_keys

printf '%s\n' 'admin ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-admin
chmod 440 /etc/sudoers.d/90-admin
visudo -cf /etc/sudoers.d/90-admin
```

**为什么给 NOPASSWD：** 服务器上的 cron（重建、watcher、备份、mail-drain）和排障命令都通过 `sudo -n docker ...` 调用；没有 NOPASSWD 时这些命令会静默卡在密码提示上。代价是任何拿到 `admin` 私钥的人都等于 root，所以 SSH 只开密钥登录。

**不要把 `admin` 加进 `docker` 组。** Docker 组等价于 root，且本项目所有脚本已经统一用 `sudo -n docker`；加组反而让「什么时候用了 root」变得不可审计。

### 3.3 验证并收紧 SSH

在本机：

```bash
ssh admin@47.82.123.169 'id; sudo -n true && echo SUDO_OK'
```

确认免密登录和 `sudo -n` 都可用后，再关闭密码登录（顺序不能反）：

```bash
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sshd -t && sudo systemctl reload ssh
```

保留控制台访问方式，直到确认新 SSH 会话能登录为止。

---

## 4. 系统初始化

以下全部在服务器上以 `admin` 执行。

### 4.1 时区、升级、基础包

```bash
sudo timedatectl set-timezone Asia/Shanghai
timedatectl | head -3

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l \
  apt-get -y full-upgrade

sudo apt-get install -y \
  ca-certificates curl gnupg git tar openssl util-linux cron rsync
```

`NEEDRESTART_MODE=l` 的作用：升级途中不让 needrestart 自动重启 docker/ssh 等服务。装 Docker 之前升级一次，装完 Docker 之后如再升级，先确认没有构建在跑。

### 4.2 swap（1.6G 机器必做）

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

grep -q '^/swapfile' /etc/fstab || \
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
```

验证：

```bash
sudo /sbin/swapon --show
free -m
```

> `swapon` 在 `/usr/sbin`，普通用户 PATH 里可能没有，直接敲 `swapon` 会报 command not found，用 `sudo /sbin/swapon`。

### 4.3 防火墙

本机**不安装 `ufw`**，历史上也没有启用过。放行只在阿里云安全组做（见 §2）。如果你坚持在系统内再拦一层，注意不要挡住 80/443，否则 Caddy 签发证书会失败。

### 4.4 时区与 cron 的关系

宿主 `/etc/timezone` 必须是 `Asia/Shanghai`，否则 §9 的 `0 4 * * *` 会静默漂到别的时间。Debian 12 是 vixie-cron 血统，**不支持 crontab 里的 `CRON_TZ=`**（写了只是塞一个没人读的环境变量）。换机后先跑 `timedatectl` 确认。

---

## 5. 安装 Docker 与 Node 22

### 5.1 Docker CE 官方源

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian bookworm stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
```

验证：

```bash
docker --version
sudo -n docker compose version
sudo -n docker run --rm hello-world
```

### 5.2 Node 22（NodeSource）

Debian 12 自带 Node 18，低于 vite-ssg 的要求，必须换源：

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

node -v
npm -v
```

期望：`v22.x`、`10.x`。宿主机 Node 只服务于 personal-web 的前端重建和 Dictionary 的前端构建；personal-mail 的前端在镜像里构建，不需要宿主 Node。

---

## 6. 拉代码

### 6.1 服务器生成 GitHub 密钥

```bash
ssh-keygen -t ed25519 -C "server-47.82.123.169" -f ~/.ssh/id_ed25519 -N ''
cat ~/.ssh/id_ed25519.pub
```

把公钥加到 GitHub：

- **推荐**：加到 GitHub 账号的 Settings → SSH and GPG keys。一个账号密钥可访问该账号有权限的所有仓库。
- 若用 Deploy key：GitHub 的 Deploy key 与仓库一对一，**同一把公钥不能同时挂到三个仓库**；需要为每个仓库生成一把并在 `~/.ssh/config` 里用 Host 别名区分。本机目前是账号密钥，最简单。

测试：

```bash
ssh -T git@github.com
```

出现 `Hi <user>! You've successfully authenticated` 即可（返回 1 是正常的，GitHub 不提供 shell）。

如果 22 端口被网络拒绝，改走 443：

```bash
ssh -T -p 443 git@ssh.github.com
```

并在 `~/.ssh/config` 写：

```sshconfig
Host github.com
  HostName ssh.github.com
  Port 443
  User git
```

之后仍用普通 `git@github.com:...` 地址即可。

### 6.2 克隆到固定路径

线上路径是约定，脚本、cron、备份都写死了这些目录：

```bash
cd ~
git clone git@github.com:LingxiReihi/personal-web.git personal-web
mkdir -p ~/personal-mail
git clone git@github.com:LingxiReihi/personal-mail.git ~/personal-mail/repo
git clone git@github.com:LingxiReihi/Dictionary.git Dictionary
```

| 项目 | 目录 | 备注 |
|---|---|---|
| personal-web | `~/personal-web` | compose 在 `deploy/`，项目名自动为 `deploy` |
| personal-mail | `~/personal-mail/repo` | **不是** `~/personal-mail`；secrets 在上一级 |
| Dictionary | `~/Dictionary` | compose 写死 `name: lexi` |

拉取纪律：每次 `git pull` 前先看 `git status --porcelain=v1 -b`，只用 `git pull --ff-only`。服务器上不允许有未提交改动；一旦出现，先查清是宿主专有配置还是别人改的，**不要 `reset --hard`**。

---

## 7. 三套服务首次部署

### 7.1 先创建共享网络

```bash
sudo -n docker network inspect lexi_net >/dev/null 2>&1 \
  || sudo -n docker network create lexi_net
```

`deploy_default` 不要手工建，personal-web 第一次 `up` 时会创建并打上 compose 标签。

### 7.2 personal-web

#### 1）后端环境变量

```bash
cd ~/personal-web
cp backend/.env.example backend/.env
```

把 `backend/.env` 改成（生产最小集）：

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
JWT_SECRET=REPLACE_WITH_openssl_rand_hex_32
ADMIN_USERNAME=admin
ADMIN_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
MEDIA_ROOT=./data/media
CORS_ORIGINS=https://www.lingxi-reihi.cn
SITE_URL=https://www.lingxi-reihi.cn
SITE_ORIGIN=https://www.lingxi-reihi.cn
REBUILD_REQUEST_FILE=/app/data/.rebuild-request
BAIDU_PUSH_API=
SEO_PUSH_ENABLED=false
```

生成密钥：

```bash
openssl rand -hex 32        # 填到 JWT_SECRET
chmod 600 backend/.env
```

要点：

- `REBUILD_SCRIPT` **必须留空**。Docker 模式的容器里没有 Node 和仓库脚本，填了只会让重建任务报 `exit=127 not found`。
- 邮件通道优先在后台「站点设置 → 邮件通道」里填（密文入库）；`.env` 里的 `MAIL_API_KEY` 只是兜底。容器内默认地址 `http://mail:8000/api/external/send` 可用（走 `lexi_net`）。
- `JWT_SECRET` 同时是邮件 API Key 密文的主密钥来源（HKDF 派生）。换 `JWT_SECRET` 后，后台里已保存的邮件 Key 解不开，需要重填一次。

`deploy/.env` 只放构建期来源：

```bash
printf 'SITE_ORIGIN=https://www.lingxi-reihi.cn\n' > deploy/.env
chmod 600 deploy/.env
```

> **必须在任何 `docker compose` 命令之前创建它。** `docker-compose.yml` 的 `builder` 服务用了 `${SITE_ORIGIN:?...}`，Compose 在解析阶段就会对整个文件做插值，所以即使只跑 `run backend` / `stop` / `logs`，缺这个变量也会直接报：
> `error while interpolating services.builder.environment.SITE_ORIGIN: required variable SITE_ORIGIN is missing`
> `deploy/.env` 被 `.gitignore` 忽略，新克隆的仓库里没有，每台新机器都要手工建一次。

#### 2）起后端并初始化

```bash
cd ~/personal-web/deploy
sudo -n docker compose up -d backend

# 等 2~3 秒，确认健康
curl -s http://127.0.0.1:8000/api/v1/health

# 建管理员 + 默认设置（幂等；已存在会 skip）
sudo -n docker compose exec -T backend python -m app.cli seed
```

容器 `CMD` 是 `alembic upgrade head && uvicorn ...`，迁移在启动时自动执行。`seed` 若创建了管理员，会把随机/配置的口令打印一次，记下来并登录后台改掉。

#### 3）构建前端

```bash
cd ~/personal-web/frontend
npm ci --no-audit --no-fund

cd ~/personal-web
APP_DIR="$PWD" \
SITE_ORIGIN=https://www.lingxi-reihi.cn \
SSG_API_BASE=http://127.0.0.1:8000/api/v1 \
bash scripts/rebuild-frontend.sh

readlink frontend/dist
```

期望末行 `rebuild ok: releases/<时间戳>`，且 `readlink` 指向同一个 release。脚本会：

- 比对 `package-lock.json` 的 sha256 前 16 位与 `node_modules/.pw-lock-sha`，不一致才 `npm ci`；
- 以 `SSG_OUT_DIR=releases/<ts>.tmp` 构建，成功后改名；
- 用 `ln -sfn` + `mv -T` 原子切换 `dist`；
- 只保留最近 3 个 release。

**构建必须能访问后端**：`SSG_API_BASE` 指向的 backend 不可达，或没有任何已发布内容，脚本会 fail-fast，不会切版本。构建期 Node 堆上限是 768 MB（脚本内 `NODE_OPTIONS`）。

#### 4）起 Caddy

```bash
cd ~/personal-web/deploy
sudo -n docker compose up -d caddy

# 校验当前宿主文件（一次性容器，避免运行中容器的旧 inode）
sudo -n docker run --rm \
  -v /home/admin/personal-web/deploy/Caddyfile:/etc/caddy/Caddyfile:ro \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile

# 看证书签发
sudo -n docker logs --tail 50 deploy-caddy-1
```

验证：

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://www.lingxi-reihi.cn/
curl -s https://www.lingxi-reihi.cn/api/v1/health
curl -sI https://lingxi-reihi.cn/ | head -3      # 应 301 到 www
```

certbot 之类不需要；Caddy 自动签发、到期前 30 天自动续期。

### 7.3 personal-mail

#### 1）授权码与宿主覆盖文件

```bash
mkdir -p ~/personal-mail/secrets
printf '%s\n' '你的QQ邮箱SMTP授权码' > ~/personal-mail/secrets/qq-secret.txt
chmod 600 ~/personal-mail/secrets/qq-secret.txt
```

QQ 邮箱 → 设置 → 账户 → 开启 SMTP 服务 → 生成授权码（不是登录密码）。

`~/personal-mail/repo/deploy/docker-compose.override.yml` **故意不入库**，由宿主维护：

```yaml
# 宿主专有覆盖，勿入库。docker compose 自动合并本文件。
services:
  mail:
    mem_limit: 128m
    # Compose 合并时 networks 是整表替换，所以两条都要列全
    networks:
      - caddy-net
      - lexi_net

networks:
  lexi_net:
    external: true
```

并在 `repo/.git/info/exclude` 里加一行 `deploy/docker-compose.override.yml`（或确认它已被排除），避免 `git status` 一直显示未跟踪文件。

#### 2）启动

```bash
cd ~/personal-mail/repo/deploy
sudo -n docker compose up -d --build
```

前置条件：`deploy_default` 已由 personal-web 创建，`lexi_net` 已存在。缺任何一个，容器会直接起不来。

验证：

```bash
curl -s https://mail.lingxi-reihi.cn/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://mail.lingxi-reihi.cn/api/settings   # 期望 401

sudo -n docker exec personal-mail python -c \
  "import sqlite3; print(sorted(r[0] for r in sqlite3.connect('/data/app.db').execute(\"select name from sqlite_master where type='table'\")))"
# 期望：['alembic_version', 'outbox', 'settings']
```

#### 3）首次登录与外部 Key

1. 打开 `https://mail.lingxi-reihi.cn`，点「获取登录验证码」。
2. 验证码发到 `login_notify_email`。仓库默认值是 `1853355058@qq.com`（`backend/app/settings_service.py` 的 `DEFAULTS`）；账号由 compose 的 `PM_ACCOUNT=orihiya@foxmail.com` 首启注入。**换部署主体时，先改 `DEFAULTS` 再构建镜像**，否则验证码会发到原站长的邮箱。
3. 登录后到设置页确认：账号、SMTP（`smtp.qq.com:465` SSL）、登录通知邮箱。
4. 到「外部接入 API」生成 Key，**明文只显示一次**，立刻保存。
5. 这个 Key 要填两处：
   - personal-web 后台「站点设置 → 邮件通道」；
   - Dictionary 的 `backend/.env` 的 `MAIL_API_KEY`。

排障：授权码失效时登录页会报 `AUTH_SEND_FAILED` / `NEED_SECRET`。若库里**从未保存过**授权码，重生成授权码、覆写 `secrets/qq-secret.txt` 后 `docker compose restart` 即可（注入只在启动时执行）。若已保存过旧授权码，`PM_SECRET_FILE` 不会覆盖它，而此时 OTP 又发不出去——临时把门禁关掉进设置页改：

在 `docker-compose.override.yml` 的 `mail` 服务下临时加：

```yaml
    environment:
      PM_AUTH_ENABLED: "0"
```

```bash
cd ~/personal-mail/repo/deploy
sudo -n docker compose up -d
# 浏览器登录设置页 → 更新授权码 / 登录通知邮箱
# 改完删掉这段 environment，恢复 PM_AUTH_ENABLED=1 后再次 up -d
```

若 `master.key` 丢失，所有会话作废且已存凭据解不开：删除卷里的 `master.key` 后重启，再重新填授权码、重置外部 Key。

**破坏性迁移提醒**：`0003_send_only` 会删除旧邮件表并清空正文缓存，`downgrade()` 是 no-op。从旧版本升级前必须先备份 `personal-mail_pm-data` 卷；从零部署不受影响。

### 7.4 Dictionary / Lexi

#### 1）后端环境变量

```bash
cd ~/Dictionary/backend
cp .env.example .env
```

生产值：

| 变量 | 值 |
|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/lexi.db`（compose 会覆盖成 `/app/data/lexi.db`） |
| `JWT_SECRET` | `openssl rand -hex 32` |
| `TIMEZONE` | `Asia/Shanghai` |
| `CORS_ORIGINS` | `https://learn.lingxi-reihi.cn` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 首次 `init` 读取；登录后立刻改 |
| `ADMIN_EMAIL` | 找回密码用 |
| `FRONTEND_DIST` | `../frontend/dist`（本机构建时）；compose 覆盖为 `/app/dist` |
| `MAIL_API_URL` | `http://mail:8000/api/external/send` |
| `MAIL_API_KEY` | personal-mail 设置页生成的 Key |
| `MAIL_DRY_RUN` | 生产 `0` |
| `REGISTER_REQUIRE_EMAIL` | 生产 `1` |

```bash
chmod 600 .env
```

#### 2）构建前端（必须在宿主做）

```bash
cd ~/Dictionary/frontend
npm ci --no-audit --no-fund
npm run build
```

产物 `frontend/dist` 会在镜像构建时 `COPY` 进去；**镜像构建不会替你跑 npm**。

#### 3）起容器

```bash
cd ~/Dictionary
sudo -n docker compose -f deploy/docker-compose.yml up -d --build
```

compose 写死 `name: lexi`，会创建 `lexi_net`；容器 `lexi-api`，宿主只绑 `127.0.0.1:8010`。首次启动自动执行 `python -m app.cli init`（建表 + 超管 + 默认设置，幂等）。

验证：

```bash
curl -s http://127.0.0.1:8010/api/v1/health
curl -s https://learn.lingxi-reihi.cn/api/v1/health
```

#### 4）Caddy 站点块

`learn.lingxi-reihi.cn` 的块已经写在 personal-web 的 `deploy/Caddyfile` 里；单独部署时把 `Dictionary/deploy/Caddyfile.snippet` 追加进去，然后重启 Caddy（见 §8）。

管理员密码重置：

```bash
sudo -n docker exec lexi-api python -m app.cli set-password admin --out /app/data/.admin-password
sudo -n cat ~/Dictionary/backend/data/.admin-password
# 读完删除
```

### 7.5 首次部署后的启动顺序复述

```bash
# ① 网络
sudo -n docker network create lexi_net 2>/dev/null || true

# ② 主站后端（创建 deploy_default）
cd ~/personal-web/deploy && sudo -n docker compose up -d backend

# ③ 邮件
cd ~/personal-mail/repo/deploy && sudo -n docker compose up -d --build

# ④ 主站 Caddy
cd ~/personal-web/deploy && sudo -n docker compose up -d caddy

# ⑤ 词书站
cd ~/Dictionary && sudo -n docker compose -f deploy/docker-compose.yml up -d --build
```

---

## 8. Caddy 统一入口

### 8.1 文件与站点块

- 宿主文件：`~/personal-web/deploy/Caddyfile`（在 git 里，改动走仓库）
- 容器内：`/etc/caddy/Caddyfile`（只读 bind mount）
- 站点块：
  - 裸域 `lingxi-reihi.cn` → 301 到 `www`
  - `http://47.82.123.169` → 301 到 `www`（只 HTTP）
  - `www.lingxi-reihi.cn` → API / media / sitemap / robots / feed / 百度验证反向代理到 `backend:8000`；其余走 `file_server` 的 `/srv/site/dist`
  - `mail.lingxi-reihi.cn` → `mail:8000`
  - `learn.lingxi-reihi.cn` → `lexi-api:8010`
- 全局 `servers { protocols h1 h2 h3 }`；compose 已映射 `443:443/udp`。
- `www` 的静态缓存策略：`/assets/*` 一年 immutable；其余（HTML、favicon）`no-store`，保证发布后立即可见。
- 安全头：`X-Content-Type-Options: nosniff`、`X-Frame-Options`、`Referrer-Policy`。

### 8.2 修改后的生效方式

```bash
cd ~/personal-web/deploy

# 1) 用一次性容器校验「当前宿主文件」。
#    不要用 docker exec 校验运行中的 caddy：编辑器若用 rename 保存，
#    运行中的容器仍挂在旧 inode 上，校验的是旧内容。
sudo -n docker run --rm \
  -v /home/admin/personal-web/deploy/Caddyfile:/etc/caddy/Caddyfile:ro \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile

# 2) 必须 restart，不是 reload
sudo -n docker compose restart caddy
sudo -n docker logs --tail 20 deploy-caddy-1
```

**为什么不能 `caddy reload`：** Caddyfile 是单文件 bind mount。宿主编辑器保存时通常「写临时文件 + rename」，容器里的挂载点还指向旧 inode；`reload` 读到的仍是旧字节，日志会显示 `config is unchanged`。`restart` 重建容器才会重新挂载，中断约 1 秒。若编辑器是原地写入（`nano`、`cat >`），`docker exec ... validate` 才有效；用上面的临时容器校验可以不受保存方式影响。

### 8.3 证书

- 证书与 ACME 账户密钥在 `deploy_caddy_data` 卷里，容器重建不丢。
- 到期前 30 天自动续期，无需 cron。
- 换机时**带着这个卷**，就不会重新签发，也不会撞 Let's Encrypt 限额。
- 阿里云 DNS 的权威服务器只在境内，LE 的多视角校验偶发解析失败，报 `During secondary validation: DNS problem`。HTTP-01 已通过说明端口和解析都对，**重试即可**；Caddy 会自动退避。
- 查证书状态：`sudo -n docker logs --tail 100 deploy-caddy-1`，搜 `certificate obtained` / `renewal information`。

### 8.4 换域名清单

1. DNS 新增 A 记录。
2. `deploy/Caddyfile` 五个块全部改。
3. `backend/.env`：`SITE_URL`、`CORS_ORIGINS`、`SITE_ORIGIN`。
4. `deploy/.env`：`SITE_ORIGIN`。
5. cron 四行里的 `SITE_ORIGIN`（重建、watcher）。
6. `Dictionary/backend/.env`：`CORS_ORIGINS`。
7. 重建前端（canonical / og:url 是构建期烤进 HTML 的）。
8. 重启 backend、caddy、lexi。

---

## 9. cron：四条定时任务

以 `admin` 执行 `crontab -e`，最终内容应与下面一致（这是 2026-11-07 线上原文）：

```cron
# 每天 04:00 重建前端；时间取系统时区（/etc/timezone=Asia/Shanghai），本机 cron 不支持 crontab 内指定时区
0 4 * * * APP_DIR=/home/admin/personal-web SITE_ORIGIN=https://www.lingxi-reihi.cn SSG_API_BASE=http://127.0.0.1:8000/api/v1 bash /home/admin/personal-web/scripts/rebuild-frontend.sh >> /home/admin/pw-rebuild.log 2>&1

# 每 5 分钟消费「发布后重建请求」
*/5 * * * * APP_DIR=/home/admin/personal-web SITE_ORIGIN=https://www.lingxi-reihi.cn bash /home/admin/personal-web/scripts/rebuild-watcher.sh >> /home/admin/pw-watcher.log 2>&1

# 每小时 15 分冲刷发信队列（避开 04:00 重建和 */5 watcher）
15 * * * * cd /home/admin/personal-web && sudo -n docker compose -f deploy/docker-compose.yml exec -T backend python -m app.cli mail-drain >> /home/admin/pw-mail-drain.log 2>&1

# 每天 03:30 备份（当前脚本有已知故障，见 §11.3）
30 3 * * * bash /home/admin/personal-web/scripts/pw-backup.sh >> /home/admin/pw-backup.log 2>&1
```

安装/修改纪律：

```bash
crontab -l > ~/pw-crontab-backup-$(date +%F-%H%M).txt   # 先留底
crontab -e
crontab -l
```

说明：

- 用 `bash <脚本>` 而不是依赖执行位：仓库在 Windows 上维护，`chmod +x` 不会进 git（存的是 644）；真在服务器补执行位，`git status` 会一直显示 mode 变更。
- `SITE_ORIGIN` 必须显式传：`sudo` 会剥离命令前缀环境变量，compose 的 `${SITE_ORIGIN:?}` 插值会回落到 `deploy/.env` 的旧值。
- `*/5` watcher 与 `0 4` 重建共用 `backend/data/.rebuild.lock`；同一时刻只有一个构建。
- 手动重建避开 03:55–04:05。撞车的典型症状是 SSH/HTTPS 集体超时（1.6G 内存双 vite-ssg）。
- 日志：`~/pw-rebuild.log`、`~/pw-watcher.log`、`~/pw-mail-drain.log`、`~/pw-backup.log`。

---

## 10. 日常发布与验证

### 10.1 personal-web 前端改动

```bash
# 本地
cd frontend && npx vue-tsc -b --force
# 提交并推送
git add <改动文件> && git commit && git push

# 服务器
cd ~/personal-web
git status --porcelain=v1 -b
git pull --ff-only

# 只有 package.json / package-lock.json 变了才需要
cd frontend && npm ci --no-audit --no-fund && cd ..

APP_DIR=/home/admin/personal-web \
SITE_ORIGIN=https://www.lingxi-reihi.cn \
SSG_API_BASE=http://127.0.0.1:8000/api/v1 \
bash scripts/rebuild-frontend.sh

readlink frontend/dist
```

线上验证：

```bash
curl -s https://www.lingxi-reihi.cn/ | grep -o '<title>[^<]*'
curl -s -o /dev/null -w '%{http_code}\n' https://www.lingxi-reihi.cn/assets/<新chunk名>.js
```

**必须查预渲染是否退化：**

```bash
R=$(basename "$(readlink ~/personal-web/frontend/dist)")
stat -c '%s %n' ~/personal-web/frontend/releases/"$R"/blog/*.html | sort -n | head
grep -o '<title>[^<]*' ~/personal-web/frontend/releases/"$R"/blog/<slug>.html
```

正常文章页是几十到几百 KB、`<title>` 是文章名。只有 ~5 KB 且标题是通用「文章 · …」说明构建期取数失败，发布的是未预渲染空壳（构建仍会 `exit 0`）。处理：确认 backend 当时可达，手动重建一次。

### 10.2 personal-web 后端改动

```bash
cd ~/personal-web
git pull --ff-only
cd deploy
sudo -n docker compose build backend
sudo -n docker compose up -d backend
```

**`up -d --force-recreate` 不会重新构建镜像。** 改了 `backend/app/**`、`requirements.txt` 或 Dockerfile，必须先 `build`。

含数据库迁移的版本，先备份（§11）。迁移由容器启动时 `alembic upgrade head` 自动执行，用日志确认版本号。

### 10.3 内容发布（自动重建）

后台发布/改状态 → 后端写 `backend/data/.rebuild-request` → 宿主 `*/5` watcher 拉起 builder 构建 → 成功后删除请求文件、原子切换 `dist`。

排查顺序：

```bash
ls -l ~/personal-web/backend/data/.rebuild-request
tail -40 ~/pw-watcher.log
```

构建日志在 `~/pw-watcher.log`：builder 是一次性容器（`run --rm`），结束后没有可回看的容器日志。job 状态停在 `requested` 是设计（消费在宿主机），不是 bug。构建失败时请求文件保留，下一轮重试。

### 10.4 personal-mail 更新

```bash
cd ~/personal-mail/repo
git status --porcelain && git pull --ff-only
cd deploy
sudo -n docker compose up -d --build
```

只改文档不需要动作；只改 compose 的 env/卷/secret 时 `up -d` 会 recreate，不必 `--build`。授权码文件更换后必须 `docker compose restart`（首启注入只读一次）。

### 10.5 Dictionary 更新

一条命令：

```bash
cd ~/Dictionary
bash scripts/deploy.sh
```

它做：`git pull --ff-only`（工作区不干净会拒绝）→ `npm ci` → `npm run build` → `docker compose up -d --build` → 30 秒健康检查。

参数：`--no-pull`、`--no-ci`、`--force`。注意 `scripts/deploy.sh` 里的 `CADDY_NETWORK` 变量目前是历史遗留：compose 已把网络名写死为 `lexi_net`，这个变量不再参与网络创建。

手动等价：

```bash
cd ~/Dictionary
git pull --ff-only
cd frontend && npm ci --no-audit --no-fund && npm run build && cd ..
sudo -n docker compose -f deploy/docker-compose.yml up -d --build
```

后端的 `core/migrate.py` 启动时会补列；v1 的 `create_all` 只建缺失的表，不会给已有表加列。

---

## 11. 数据、卷与备份

### 11.1 必须备份的东西

| 内容 | 位置 | 丢了会怎样 |
|---|---|---|
| 主站库 + 素材 | `~/personal-web/backend/data/`（`app.db`、`media/`、`logs/`） | 内容、用户、评论、公告、统计、上传文件全丢 |
| 主站配置 | `~/personal-web/backend/.env`、`~/personal-web/deploy/.env` | 密钥/域名重建；`JWT_SECRET` 换了所有人被登出 |
| 邮件配置 | `~/personal-mail/secrets/qq-secret.txt` | 首次注入失效；已保存过则不影响 |
| 邮件卷 | `personal-mail_pm-data` | `master.key` 丢失后已存凭据永久解不开；outbox 记录丢失 |
| 词书站数据 | `~/Dictionary/backend/data/`（`lexi.db` + `-wal` + `-shm`，可能还有 `.admin-password`） | 词书/学习记录全丢；主库只有几 MB，**大量数据在未合并的 `-wal` 里，直接 tar 主库会备到空库** |
| 词书配置 | `~/Dictionary/backend/.env` | `JWT_SECRET`、邮件 Key 丢失 |
| Caddy 卷 | `deploy_caddy_data`、`deploy_caddy_config` | LE 证书 + ACME 账户密钥；重签可能撞限额 |
| SSH | `~/.ssh/id_ed25519`、`authorized_keys` | 新机拉不动代码、自己登不进去 |
| crontab | `crontab -l` 原文 | 四条定时任务重装即丢 |

不需要备份：`node_modules/`、`.venv/`、`frontend/releases/`（可重建）、Docker 镜像、`deploy_node_modules`、`deploy_npm_cache`。

### 11.2 备份脚本

脚本：`~/personal-web/scripts/pw-backup.sh`，产物目录 `~/pw-backups`（700，包 600），保留 14 天（`PW_BACKUP_KEEP_DAYS` 可调）。

```bash
mkdir -p ~/pw-backups && chmod 700 ~/pw-backups
bash ~/personal-web/scripts/pw-backup.sh
```

它做的事：

1. 确认 `deploy-backend-1` 在跑，否则直接失败；
2. 三枚 SQLite 全部借容器里的 python 走 `sqlite3.Connection.backup()` 取**一致快照**（宿主机没有 `sqlite3` CLI，也绝不 `tar` 正在写的 `-wal`）；**当前脚本在 mail 这一段有一处已知故障，见 §11.3**；
3. 三枚快照都过 `PRAGMA integrity_check`，不过就非零退出、当天不产出包；
4. 打三个卷：`personal-mail_pm-data`、`deploy_caddy_data`、`deploy_caddy_config`；
5. 收 `crontab -l`、两套 `.env`、mail secrets、SSH 密钥；
6. 产出 `pw-<日期>.tar.gz` + `.list` + `.sha256`；
7. 清理超过保留期的旧包。

`lexi-api` 没在跑时只记 warn 跳过词书站，不让别的停机把主站备份拖失败。

**它防什么：** 误删、库损坏、发布出事。**不防**磁盘/实例丢失——备份和原库在同一块盘。异地副本要靠云快照或 `scp/rclone`，且异地那份同样含明文密钥，必须先加密。

```bash
openssl enc -aes-256-cbc -md sha256 -pbkdf2 -iter 600000 \
  -in ~/pw-backups/pw-2026-11-07.tar.gz \
  -out ~/pw-backups/pw-2026-11-07.tar.gz.enc \
  -pass file:/path/to/passphrase
```

### 11.3 当前已知故障（2026-11-07，未修复）

**每日备份从 2026-10-29 起连续失败；最后一次成功包是 `pw-2026-10-28.tar.gz`，此后没有产出任何整包。** 证据：

```text
[pw-backup] 2026-11-07 03:30:01 start ts=2026-11-07 ...
main db: integrity=ok contents=20 users=3
Traceback (most recent call last):
  File "<stdin>", line 7, in <module>
sqlite3.OperationalError: no such table: messages
[pw-backup] 2026-11-07 03:30:01 FATAL: personal-mail 库快照失败或 integrity_check 未通过
```

根因：personal-mail 的 `0003_send_only` 迁移删除了 `messages` 表，但 `scripts/pw-backup.sh` 里仍执行 `SELECT COUNT(*) FROM messages`。当前 personal-mail 库只有 `alembic_version`、`outbox`、`settings` 三张表。因为轮换代码在打包成功之后才执行，失败期间旧包也不会被清理——所以 `~/pw-backups` 里仍留着 10-26/27/28 三个包，看起来「还有备份」，实际最新已过期 10 天。

**建议修复（本轮未实施）：** 把计数查询改成 `outbox`：

```diff
-    m = d.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
-    print("mail db: integrity=%s messages=%s" % (ok, m))
+    m = d.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
+    print("mail db: integrity=%s outbox=%s" % (ok, m))
```

改完提交、服务器 `git pull --ff-only`，然后手动跑一次：

```bash
bash ~/personal-web/scripts/pw-backup.sh
tail -20 ~/pw-backup.log
ls -l ~/pw-backups/pw-$(date +%F).*
```

只有日志出现三枚库的 `integrity=ok` 且末行 `ok ts=... size=... members=...`，并实际看到 `pw-<日期>.tar.gz`、`.list`、`.sha256`，才算恢复。**不要只看 cron 有没有执行。**

### 11.4 恢复演练

先解包到临时目录查看成员：

```bash
mkdir -p /tmp/pwrestore
tar xzf ~/pw-backups/pw-<日期>.tar.gz -C /tmp/pwrestore
tar tzf ~/pw-backups/pw-<日期>.tar.gz | head -30
```

包内成员是相对路径，分别落在三个根下：`backend/...` 和 `deploy/.env` 属于 `~/personal-web`，`secrets/` 属于 `~/personal-mail`，`authorized_keys` / `id_ed25519*` 属于 `~/.ssh`。

#### 主站库

```bash
sudo -n docker compose -f ~/personal-web/deploy/docker-compose.yml stop backend

# 素材与日志（可选，按需覆盖；注意源路径末尾的 /.，避免套娃成 media/media）
cp -a /tmp/pwrestore/backend/data/media/. ~/personal-web/backend/data/media/
cp -a /tmp/pwrestore/backend/data/logs/.  ~/personal-web/backend/data/logs/

# 用干净快照覆盖主库，不要用 backend/data 里那份可能写了一半的 app.db
cp /tmp/pwrestore/app-<日期>.db ~/personal-web/backend/data/app.db
rm -f ~/personal-web/backend/data/app.db-wal ~/personal-web/backend/data/app.db-shm

sudo -n docker compose -f ~/personal-web/deploy/docker-compose.yml up -d backend
```

**替换库时必须同时删旧 `-wal` / `-shm`**，否则新库配旧 WAL 语义不明。主站 `backend/data` 属主是 `admin`，上面的 `cp` 不需要 sudo；如果之前用 root 解包过，记得 `chown admin:admin`，否则每日备份（以 `admin` 读 `backend/.env` 与 data）会失败。

#### personal-mail 卷

```bash
cd ~/personal-mail/repo/deploy
sudo -n docker compose stop mail
sudo -n docker volume create personal-mail_pm-data
sudo -n sh -c 'rm -rf /var/lib/docker/volumes/personal-mail_pm-data/_data/* \
  /var/lib/docker/volumes/personal-mail_pm-data/_data/.[!.]*'
sudo -n tar xf /tmp/pwrestore/volumes-<日期>.tar -C /var/lib/docker/volumes

# 卷 tar 里的 app.db 可能不一致，再用干净快照覆盖
sudo -n cp /tmp/pwrestore/pm-app-<日期>.db \
  /var/lib/docker/volumes/personal-mail_pm-data/_data/app.db
sudo -n rm -f \
  /var/lib/docker/volumes/personal-mail_pm-data/_data/app.db-wal \
  /var/lib/docker/volumes/personal-mail_pm-data/_data/app.db-shm

sudo -n docker compose up -d
```

`volumes-<日期>.tar` 含 `personal-mail_pm-data/_data`、`deploy_caddy_data/_data`、`deploy_caddy_config/_data`。**日常恢复主站数据时不要动后两个卷**；只有整机迁移才恢复证书卷，且必须在 caddy 停止时做。卷目录属主是 root，全部走 `sudo -n`。

#### 词书站

```bash
cd ~/Dictionary
sudo -n docker compose -f deploy/docker-compose.yml stop
sudo -n tar xzf /tmp/pwrestore/lexi-<日期>.tar.gz -C ~/Dictionary
sudo -n cp /tmp/pwrestore/lexi-<日期>.db ~/Dictionary/backend/data/lexi.db
sudo -n rm -f ~/Dictionary/backend/data/lexi.db-wal ~/Dictionary/backend/data/lexi.db-shm
sudo -n docker compose -f deploy/docker-compose.yml up -d
```

`lexi-<日期>.tar.gz` 里是 `backend/data` 与 `backend/.env`；容器写出的 `lexi.db*` 属主是 root，解包和替换都要 `sudo`。

#### 恢复后验证

```bash
curl -s http://127.0.0.1:8000/api/v1/health
curl -s http://127.0.0.1:8010/api/v1/health
curl -s https://mail.lingxi-reihi.cn/api/health
sudo -n docker exec personal-mail python -c \
  "import sqlite3; print(sqlite3.connect('/data/app.db').execute('PRAGMA integrity_check').fetchone())"
```

---

## 12. 整机迁移 / 更换系统盘

单盘实例「更换操作系统」= 全盘初始化，机器上的任何副本都会一起消失。按下面顺序做，**不要跳步**。

1. **打云快照**（唯一回滚依据），然后把 `~/pw-backups` 拉到本地并 `sha256sum -c` 校验。异地一份。
2. 本地解包，用 `PRAGMA integrity_check` + 表计数复验（主站 contents/users、mail outbox、lexi 各表）。**校验不过就别开始重装。**
3. 新机按 §3 建用户/回填公钥/写 sudoers；本地先 `ssh-keygen -R 47.82.123.169`（host key 变了）。
4. 按 §4 配时区、swap、`/etc/fstab`、`vm.swappiness`；按 §5 装 Docker 和 Node 22。
5. 恢复 `~/.ssh/id_ed25519` 与 `authorized_keys`（600/700），先 `ssh -T git@github.com` 验旧密钥还能用；不能用就按 §6 生成新密钥、加到 GitHub，再拉三个仓库。
6. 恢复配置：`~/personal-web/backend/.env`、`~/personal-web/deploy/.env`、`~/personal-mail/secrets/qq-secret.txt`（600）、`~/Dictionary/backend/.env`。
7. 恢复数据：主站 `backend/data/`、词书 `backend/data/`；替换库时删 `-wal`/`-shm`。优先用包里的干净快照 `app-*.db` / `pm-app-*.db` / `lexi-*.db`，不要用卷 tar 里可能写了一半的 `app.db`。
8. 恢复卷（容器必须停止）：
   ```bash
   for v in personal-mail_pm-data deploy_caddy_data deploy_caddy_config; do
     sudo -n docker volume create "$v"
   done

   # 目标卷已有内容时先清空；新机/新卷可跳过这行
   sudo -n sh -c 'for v in personal-mail_pm-data deploy_caddy_data deploy_caddy_config; do \
     rm -rf /var/lib/docker/volumes/$v/_data/* /var/lib/docker/volumes/$v/_data/.[!.]*; done'

   sudo -n tar xf /tmp/pwrestore/volumes-<日期>.tar -C /var/lib/docker/volumes
   ```
   带上证书卷就不会重签，避免 Let's Encrypt 限额。恢复完仍要用干净快照覆盖 `personal-mail_pm-data/_data/app.db`（删 `-wal`/`-shm`），不要直接用卷 tar 里可能写了一半的库。
9. 恢复 `dist` 符号链接：把当前 release 一起搬过去，`ln -sfn releases/<时间戳> dist`，先能出页，不必立刻赌一次构建（1.6G 内存跑 vite-ssg 有 OOM 风险）。
10. 恢复 crontab：`crontab /tmp/pwrestore/crontab-<日期>.txt`，逐行核对路径与 `SITE_ORIGIN`。
11. 按 §1.2 顺序启动；首次启动前确认 `lexi_net` 存在。

收口验证：

```bash
timedatectl | head -3
sudo /sbin/swapon --show
sudo -n docker ps --format 'table {{.Names}}\t{{.Status}}'
sudo -n docker network ls
crontab -l

curl -s -o /dev/null -w 'www %{http_code}\n' https://www.lingxi-reihi.cn/
curl -s -o /dev/null -w 'mail %{http_code}\n' https://mail.lingxi-reihi.cn/api/health
curl -s -o /dev/null -w 'learn %{http_code}\n' https://learn.lingxi-reihi.cn/api/v1/health
```

再查一次预渲染页面的体积与 `<title>`（§10.1 末段），以及 `releases/` 是否存在 5 KB 空壳。

---

## 13. 升级与回滚

### 13.1 通用纪律

- 含数据库迁移的版本，升级前先跑一次备份（§11），并确认 `integrity=ok`。
- `git pull --ff-only`；不 force、不 reset。
- 后端代码变更必须 `compose build`，不能只 `up -d`。
- 前端 canonical / og:url / 预渲染内容是构建期烤进 HTML 的，改域名或模板后必须重建。

### 13.2 personal-web

后端：

```bash
cd ~/personal-web/deploy
sudo -n docker compose build backend
sudo -n docker compose up -d backend
sudo -n docker compose logs --tail 50 backend
```

前端：

```bash
APP_DIR=/home/admin/personal-web SITE_ORIGIN=https://www.lingxi-reihi.cn \
SSG_API_BASE=http://127.0.0.1:8000/api/v1 \
bash ~/personal-web/scripts/rebuild-frontend.sh
```

回滚前端（秒级，不用重新构建）：

```bash
cd ~/personal-web/frontend
ls -1t releases/
ln -sfn releases/<上一个好版本> dist.tmp && mv -T dist.tmp dist
```

回滚代码：`git checkout <tag/commit>` 后重复升级步骤；alembic 可用 `alembic downgrade -1`，不支持的迁移只能靠备份恢复。

### 13.3 personal-mail

```bash
cd ~/personal-mail/repo && git pull --ff-only
cd deploy && sudo -n docker compose up -d --build
```

破坏性迁移（0003）回滚**不能只回代码**：旧镜像入口也会执行 `alembic upgrade head`，而库版本已是 0003。必须同时恢复升级前的 `pm-data` 卷（§11.4），否则旧代码会因表已删除而启动失败。

### 13.4 Dictionary

```bash
cd ~/Dictionary
bash scripts/deploy.sh
# 或
git pull --ff-only
cd frontend && npm ci && npm run build && cd ..
sudo -n docker compose -f deploy/docker-compose.yml up -d --build
```

v1 的 `create_all` 只新建缺失表，不会给已有表加列；需要加列时手写 `ALTER TABLE` 并在 `docs/` 留记录。

---

## 14. 故障排查

| 症状 | 根因 | 处置 |
|---|---|---|
| `error while interpolating services.builder.environment.SITE_ORIGIN: required variable SITE_ORIGIN is missing` | `deploy/.env` 不存在（被 `.gitignore` 忽略）；Compose 解析整个文件，任何子命令都会先插值 | 在 `deploy/` 下创建 `SITE_ORIGIN=https://域名` 的 `.env`，再重跑；见 §7.2 |
| 备份日志 `no such table: messages`，整包不产出 | `pw-backup.sh` 仍查已删除的 mail `messages` 表 | §11.3 改成 `outbox`；修好前不要宣称备份可用 |
| `www` 502 | `deploy-backend-1` 没起 / 崩了 | `sudo -n docker compose -f ~/personal-web/deploy/docker-compose.yml logs --tail 100 backend` |
| `mail` 502 | `personal-mail` 没起，或不在 `deploy_default` 上 | `sudo -n docker ps`；`docker inspect personal-mail -f '{{json .NetworkSettings.Networks}}'` |
| `learn` 502 | `lexi-api` 没起，或不在 `lexi_net` 上 | `sudo -n docker logs --tail 100 lexi-api`；检查网络 |
| `personal-web` 启动报 `network lexi_net ... could not be found` | 外部网络没建 | `sudo -n docker network create lexi_net` |
| `personal-mail` 启动报 `network deploy_default ... could not be found` | personal-web 还没起 | 先起 `deploy` 的 backend |
| `docker: permission denied` | `admin` 不在 docker 组（设计如此） | 一律 `sudo -n docker ...` |
| 后端代码改了线上无效 | 只 `up -d --force-recreate`，没重打镜像 | `compose build backend` 后 `up -d backend` |
| Caddyfile 改了不生效，日志 `config is unchanged` | 单文件 bind mount 旧 inode | `docker compose restart caddy`，不是 `reload` |
| 证书签发失败 `During secondary validation: DNS problem` | 阿里云权威 DNS 只在境内，LE 二视角偶发失败 | 确认 HTTP-01 可达后重试；Caddy 自动退避 |
| 发布后前台还是旧页 | `dist` 没切 / 客户端缓存 | `readlink frontend/dist`；Ctrl+F5 |
| 重建 `rebuild ok` 但文章页 5 KB、标题通用 | 构建期取数失败，静默退化成空壳 | 确认 backend 可达；手动重建；上线后必查体积 |
| 构建/站点集体失联，SSH 也卡 | 04:00 cron 与手动重建撞车，双 vite-ssg OOM | 等恢复；之后避开 04:00；确认 `flock` 在位 |
| watcher 越跑越慢、`ETIMEDOUT` | 历史问题：冷缓存 `npm ci` > 5 分钟，cron 自叠 | 已由持久卷 `npm_cache` + `flock` 根治；异常时查 `docker ps \| grep builder` 与 `npm_cache` |
| 忘记密码返回「邮件通道未配置」 | 后台 mail 设置组为空 | 在「站点设置 → 邮件通道」填 URL + Key；补管理员邮箱 |
| 邮件外部接口 403 `EXTERNAL_DISABLED` | 从未生成外部 Key | personal-mail 设置页生成 Key |
| 改 `JWT_SECRET` 后所有人被登出 | 预期行为 | 重新登录；后台邮件 Key 需重填 |
| 词书站时间/日期不对 | `TIMEZONE` 与服务器时区不一致 | 改 `Dictionary/backend/.env` 后重启 |
| 词书站页面 404 但 API 正常 | `frontend/dist/index.html` 不存在 | 宿主重新 `npm run build` 并重建镜像 |
| 登录态丢失/凭据解不开（mail） | `pm-data` 里的 `master.key` 被删/换 | 从备份恢复卷；否则重填授权码、重置外部 Key |
| `swapon: command not found` | 不在普通用户 PATH | `sudo /sbin/swapon --show` |
| 直接 `tar` 正在写的 SQLite 导致库损坏 | WAL 未合并 | 用容器内 python 的 `backup()` 取快照；替换库时删 `-wal`/`-shm` |
| `docker volume prune` 后证书/密钥消失 | 卷被清 | **绝不要 prune**；只清 `frontend/releases/` 和构建缓存 |
| 服务器 `git pull` 报工作区有改动 | 宿主专有配置或手工修改 | 先 `git diff` 定性；必要时搬进 override，禁止 `reset --hard` |

---

## 15. 安全检查清单

- [ ] SSH 仅密钥登录；`authorized_keys` 权限 600、`.ssh` 700。
- [ ] `admin` 有 NOPASSWD sudo，但**不在 docker 组**（设计如此）。
- [ ] 阿里云安全组只放行 22（限来源）/80/443 TCP，可选 443 UDP；8000/8010 不暴露公网。
- [ ] `personal-web/backend/.env`、`deploy/.env`、`Dictionary/backend/.env`、`qq-secret.txt` 权限 600，且都在 git 之外。
- [ ] `JWT_SECRET` 为 `openssl rand -hex 32`，不是模板值。
- [ ] 三套管理员初始密码已改；personal-web 管理员邮箱已填（忘记密码需要）。
- [ ] personal-mail 的 OTP 登录通知邮箱已确认；外部 Key 只存密文，明文只显示一次。
- [ ] `~/pw-backups` 700、备份包 600；有异地加密副本。
- [ ] 云快照策略在位；最近一次恢复演练有记录。
- [ ] Caddy 安全响应头在位；`JWT_SECRET`/授权码/口令没有出现在截图或聊天里（如出现，轮换）。

---

## 16. 上线验收清单（从零部署收口）

按顺序执行，每条都要看到期望结果：

1. `ssh admin@47.82.123.169 'id; sudo -n true && echo SUDO_OK'` → `SUDO_OK`
2. `timedatectl | head -3` → `Asia/Shanghai`
3. `sudo /sbin/swapon --show` → 有 2G swap
4. `sudo -n docker ps` → 四个容器：`deploy-caddy-1`、`deploy-backend-1`、`personal-mail`、`lexi-api`
5. `sudo -n docker network ls` → `deploy_default`、`lexi_net`
6. `curl -s http://127.0.0.1:8000/api/v1/health` → `{"code":0...}`
7. `curl -s http://127.0.0.1:8010/api/v1/health` → `{"code":0...}`
8. `curl -s https://mail.lingxi-reihi.cn/api/health` → 200
9. `curl -s -o /dev/null -w '%{http_code}' https://mail.lingxi-reihi.cn/api/settings` → 401
10. `curl -sI https://lingxi-reihi.cn/` → 301 到 `https://www.lingxi-reihi.cn/`
11. `curl -s https://www.lingxi-reihi.cn/ | grep -o '<title>[^<]*'` → 站点标题
12. `R=$(basename "$(readlink ~/personal-web/frontend/dist)"); stat -c '%s %n' ~/personal-web/frontend/releases/"$R"/blog/*.html | sort -n | head` → 至少几十 KB，不是 5 KB
13. `grep -o '<title>[^<]*' .../blog/<slug>.html` → 文章名
14. `crontab -l` → 四条任务齐全，路径与域名正确
15. `tail -20 ~/pw-backup.log` → 在备份故障修复前会看到 FATAL（见 §11.3）；修好后应见 `ok ts=...`
16. `sudo -n docker volume ls` → 至少 `personal-mail_pm-data`、`deploy_caddy_data`、`deploy_caddy_config`、`deploy_node_modules`、`deploy_npm_cache`
17. 三个仓库 `git status --porcelain` → 干净
18. 浏览器登录三个后台各一次（www 后台、mail OTP、learn 后台）→ 成功

---

## 附录 A：路径 / 端口 / 卷速查

| 项 | 值 |
|---|---|
| 服务器 | `admin@47.82.123.169` |
| 主站代码 | `/home/admin/personal-web` |
| 主站 compose | `/home/admin/personal-web/deploy/docker-compose.yml`（项目名 `deploy`） |
| 主站 Caddyfile | `/home/admin/personal-web/deploy/Caddyfile` |
| 主站数据 | `/home/admin/personal-web/backend/data` |
| 主站前端 | `/home/admin/personal-web/frontend/dist` → `releases/<ts>` |
| 邮件代码 | `/home/admin/personal-mail/repo` |
| 邮件 compose | `/home/admin/personal-mail/repo/deploy/docker-compose.yml`（项目名 `personal-mail`） |
| 邮件宿主覆盖 | `/home/admin/personal-mail/repo/deploy/docker-compose.override.yml`（不入库） |
| 邮件授权码 | `/home/admin/personal-mail/secrets/qq-secret.txt`（600） |
| 词书代码 | `/home/admin/Dictionary` |
| 词书 compose | `/home/admin/Dictionary/deploy/docker-compose.yml`（项目名 `lexi`） |
| 词书数据 | `/home/admin/Dictionary/backend/data/lexi.db` |
| 备份目录 | `/home/admin/pw-backups` |
| 备份脚本 | `/home/admin/personal-web/scripts/pw-backup.sh` |
| 重建脚本 | `/home/admin/personal-web/scripts/rebuild-frontend.sh` |
| watcher | `/home/admin/personal-web/scripts/rebuild-watcher.sh` |
| 日志 | `~/pw-rebuild.log`、`~/pw-watcher.log`、`~/pw-mail-drain.log`、`~/pw-backup.log` |

| 卷 / 网络 | 说明 |
|---|---|
| `deploy_caddy_data` | LE 证书 + ACME 账户密钥（不可再生） |
| `deploy_caddy_config` | Caddy 配置缓存 |
| `deploy_node_modules` | builder 的 `node_modules` |
| `deploy_npm_cache` | builder 的 npm 缓存（冷装 13 分钟 → 10 秒） |
| `personal-mail_pm-data` | mail 的 `/data`（含 `master.key`） |
| `deploy_default` | personal-web 创建，mail 加入 |
| `lexi_net` | Dictionary 创建，personal-web / mail 加入 |

---

## 附录 B：环境变量速查

### B.1 personal-web（`backend/.env`）

| 变量 | 生产值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | 相对 backend 工作目录 |
| `JWT_SECRET` | `openssl rand -hex 32` | 同时是邮件 Key 密文主密钥来源 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / 强密码 | 仅 `seed` 首次读取 |
| `MEDIA_ROOT` | `./data/media` | 素材落盘 |
| `CORS_ORIGINS` | `https://www.lingxi-reihi.cn` | 同域反代其实用不到，留作直连场景 |
| `SITE_URL` | `https://www.lingxi-reihi.cn` | sitemap/RSS/推送基址 |
| `SITE_ORIGIN` | 同 `SITE_URL` | cron/重建脚本用；Docker 模式下后端不读也可留 |
| `REBUILD_REQUEST_FILE` | `/app/data/.rebuild-request` | Docker watcher 模式必填 |
| `REBUILD_SCRIPT` | **空** | Docker 模式填了会 `exit=127` |
| `REBUILD_MERGE_SECONDS` | `10` | 发布合并窗口 |
| `BAIDU_PUSH_API` / `SEO_PUSH_ENABLED` | token / `true` | 没 token 时留空/false |
| `BAIDU_VERIFY_NAME` / `BAIDU_VERIFY_CONTENT` | 百度验证文件 | 后端直出 |
| `MAIL_API_URL` | `http://mail:8000/api/external/send` | 后台设置优先，这里兜底 |
| `MAIL_API_KEY` | 空（后台填） | 密文入库优先 |
| `MAIL_OVERRIDE_TO` | 空 | 排障用，线上必须空 |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `120` / `7` | 登录态 |

### B.2 personal-mail

| 变量 | 来源 | 说明 |
|---|---|---|
| `PM_AUTH_ENABLED` | compose | `1` 开启 OTP 登录门禁 |
| `PM_SECRET_FILE` | compose | `/run/secrets/qq_secret` |
| `PM_ACCOUNT` | compose | 首次注入 SMTP 账号（`orihiya@foxmail.com`） |
| `PM_HOST` / `PM_PORT` | Dockerfile | `0.0.0.0` / `8000` |
| `PM_DATA_DIR` | Dockerfile | `/data` |
| `PM_FRONTEND_DIST` | Dockerfile | `/app/dist` |
| `PM_SECRET_BACKEND` | Dockerfile | `fernet`（Linux 无 DPAPI，用 Fernet） |
| `PM_LOG_LEVEL` | 可选 | `Settings` 的 `PM_` 前缀字段 |

授权码、外部 Key、SMTP 主机/端口/安全方式、登录通知邮箱都在 `settings` 表（设置页维护），不在环境变量里。

### B.3 Dictionary（`backend/.env`）

| 变量 | 生产值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/lexi.db` | compose 覆盖为 `/app/data/lexi.db` |
| `JWT_SECRET` | `openssl rand -hex 32` | 改后所有登录态失效 |
| `TIMEZONE` | `Asia/Shanghai` | 「今天」的切分 |
| `CORS_ORIGINS` | `https://learn.lingxi-reihi.cn` | 不含 `*` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / 强密码 | 仅首次 `init` |
| `ADMIN_EMAIL` | 管理员邮箱 | 找回密码 |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `120` / `14` | 登录态 |
| `FRONTEND_DIST` | `../frontend/dist` | compose 覆盖为 `/app/dist` |
| `MAX_IMPORT_ROWS` / `MAX_IMPORT_BYTES` | `5000` / `5242880` | 导入限制 |
| `MAIL_API_URL` | `http://mail:8000/api/external/send` | 同机容器别名 |
| `MAIL_API_KEY` | personal-mail 生成 | 不填则注册/找回密码不可用 |
| `MAIL_DRY_RUN` | `0` | 本地无邮件服务时置 1 |
| `REGISTER_REQUIRE_EMAIL` | `1` | 注册邮箱验证 |
| `MAIL_CODE_TTL_MINUTES` / `MAIL_CODE_COOLDOWN_SECONDS` | `10` / `60` | 验证码 |

---

## 附录 C：已知问题与文档漂移

1. **备份脚本连续失败（当前最高优先级）**：`scripts/pw-backup.sh` 仍查已删除的 mail `messages` 表；2026-10-29 起每天 03:30 失败、不产出整包，最后成功包是 10-28。修复见 §11.3，**尚未实施**。
2. **personal-mail 的 `docker-compose.override.yml` 不在 git 里**：`mem_limit: 128m` 与 `lexi_net` 只存在于服务器。`git checkout` / `reset --hard` 会抹掉它，导致 mail 脱离 `lexi_net`、lexi 发信断链。拉取前先看 `git status`。
3. **Dictionary 的 `docs/deployment.md` 有历史表述**：仍提到 `CADDY_NETWORK=personal-web_default`、把 lexi 挂到 personal-web 默认网络。当前实际是独立 `lexi_net`，`CADDY_NETWORK` 不再参与网络创建；以本手册与 `deploy/docker-compose.yml` 为准。
4. **宿主机没有 `sqlite3` CLI**：所有查库/快照走 `sudo -n docker exec ... python -`，不要照抄任何 `sqlite3` 命令行脚本。
5. **`swapon` 不在普通用户 PATH**：用 `sudo /sbin/swapon --show`。
6. **内核版本以 `uname -r` 为准**：本文实测 `6.1.0-33-amd64`；升级后会变，不影响部署步骤。
7. **`docker compose up -d --force-recreate` 不重建镜像**：后端代码变更必须 `build`。
8. **Caddyfile 是单文件 bind mount**：改完必须 `restart caddy`，`reload` 读旧 inode。
9. **personal-mail 的 OTP 默认通知邮箱写死在 `DEFAULTS`**：换部署主体时先改 `backend/app/settings_service.py` 再构建镜像，否则验证码发到原站长邮箱。
10. **`deploy_caddy_data` / `personal-mail_pm-data` 不可再生**：任何清理都不要 `docker volume prune`；只清 `frontend/releases/` 与构建缓存。
