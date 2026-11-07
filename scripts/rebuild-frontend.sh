#!/usr/bin/env bash
# 前端本机重建（docs/backend-architecture.md §10.3 v1.2 时序）
# 用法：后端 REBUILD_SCRIPT 指向本脚本绝对路径；需 Node >= 20、可用内存 >= 1GB。
# 约定目录布局：$APP_DIR/{frontend,backend}；Caddy root 指向 $APP_DIR/frontend/dist（符号链接）。
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/personal-web}"
SSG_API_BASE="${SSG_API_BASE:-http://127.0.0.1:8000/api/v1}"
SITE_ORIGIN="${SITE_ORIGIN:?SITE_ORIGIN 未设置（如 https://example.com），写入 /etc/environment 或本脚本头部}"
KEEP_RELEASES=3

# 同一时刻只允许一个构建。两条调用路径都过这把锁：宿主 `0 4` cron 直接跑本脚本，
# watcher 通过 builder 容器跑（容器里 APP_DIR=/repo，是宿主 $APP_DIR 的 bind mount），
# 所以锁放在 backend/data/（已被 .gitignore 忽略）——两边看到的是同一个 inode。
# 拿不到锁要**非零**退出：watcher 靠退出码决定删不删 .rebuild-request，
# 若把「被跳过」报成成功，这次内容就永远不会被重建了。
LOCK_FILE="$APP_DIR/backend/data/.rebuild.lock"
( umask 002; : >> "$LOCK_FILE" ) 2>/dev/null || true
chmod 666 "$LOCK_FILE" 2>/dev/null || true   # 宿主 admin 与容器 root 都要能打开
if ! exec 9>"$LOCK_FILE"; then
  echo "rebuild FAILED: 打不开锁文件 $LOCK_FILE" >&2
  exit 4
fi
if ! flock -n 9; then
  echo "rebuild skipped: 另一个构建正持有 $LOCK_FILE" >&2
  exit 3
fi

cd "$APP_DIR/frontend"
export SSG_API_BASE
export VITE_SSG_API_BASE="$SSG_API_BASE"
export VITE_SITE_ORIGIN="$SITE_ORIGIN"
# 1.6G 小机：给 Node 建堆上限，避免构建期整机内存被吃满
export NODE_OPTIONS="${NODE_OPTIONS:-} --max-old-space-size=768"

# 依赖守卫：比对 lock 摘要，而不是只探测 .bin 在不在。
# 只探测 vite-ssg 会被「卷里装过一批旧依赖」骗过：2026-10-06 卷里缺 jszip，守卫判真
# 跳过安装，构建必失败且 watcher 每 5 分钟重试一次，连撞 32 次才被人看见。
# 指纹落在 node_modules 内 —— npm ci 会连它一起清掉，所以只在安装成功后盖章。
LOCK_SHA="$(sha256sum package-lock.json | cut -c1-16)"
STAMP="node_modules/.pw-lock-sha"
if [ ! -x node_modules/.bin/vite-ssg ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$LOCK_SHA" ]; then
  npm ci --no-audit --no-fund
  printf '%s' "$LOCK_SHA" > "$STAMP"
fi

REL="releases/$(date +%Y%m%d%H%M%S)"
rm -rf "$REL.tmp"
# vite-ssg 构建（拉取 published 内容枚举路由；后端不可达会 fail-fast 退出非 0）
# 页面渲染已在 vite.config.ts 里串行；这里再降 CPU/IO 优先级，构建期间不拖垮站点
BUILD_CMD=(nice -n 19)
if command -v ionice >/dev/null 2>&1 && ionice -c 3 true 2>/dev/null; then
  BUILD_CMD+=(ionice -c 3)
fi
echo "build mem before: $(free -m | awk '/^Mem:/{printf "used=%sMB avail=%sMB", $3, $7}')"
SSG_OUT_DIR="$REL.tmp" "${BUILD_CMD[@]}" npx vite-ssg build
echo "build mem after:  $(free -m | awk '/^Mem:/{printf "used=%sMB avail=%sMB", $3, $7}')"
mv "$REL.tmp" "$REL"

# 原子切换 dist 符号链接
# -T 必需：dist 是指向目录的符号链接，mv 默认会跟随目录把 dist.tmp 移进去而非替换链接
ln -sfn "$REL" dist.tmp
mv -T dist.tmp dist

# 清理旧版本（保留最近 N 个）
ls -1t releases | tail -n +$((KEEP_RELEASES + 1)) | while read -r old; do rm -rf "releases/$old"; done

echo "rebuild ok: $REL"
