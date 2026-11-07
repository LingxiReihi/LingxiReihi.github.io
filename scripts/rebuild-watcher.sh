#!/usr/bin/env bash
# 宿主机重建 watcher（Docker 模式，docs/deployment.md §4-D）
# 后端容器无法在自身内跑 Node 构建，改为发布时写「重建请求文件」到共享卷 backend/data/，
# 本脚本由宿主机 cron 定时轮询：发现请求 → 拉起 builder 容器全量重建 → 成功后清除请求。
# 装法（宿主机 crontab -e，替换域名与路径）：
#   */5 * * * * APP_DIR=/home/admin/personal-web SITE_ORIGIN=https://你的域名 bash /home/admin/personal-web/scripts/rebuild-watcher.sh >> /home/admin/pw-watcher.log 2>&1
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/personal-web}"
# 容器内 /app/data = 宿主 backend/data；后端写的是 .rebuild-request
REQUEST_FILE="${REQUEST_FILE:-$APP_DIR/backend/data/.rebuild-request}"
SITE_ORIGIN="${SITE_ORIGIN:?SITE_ORIGIN 未设置（如 https://your-domain）}"

# 无请求则静默退出（cron 每 5 分钟空跑代价极低）
[ -f "$REQUEST_FILE" ] || exit 0

echo "watcher: rebuild request detected $(date -u +%FT%TZ), urls:"
cat "$REQUEST_FILE"

cd "$APP_DIR/deploy"
# cron 的 admin 用户不在 docker 组时用 sudo -n（NOPASSWD）；已在组内可 DOCKER=docker 覆盖
DOCKER="${DOCKER:-sudo -n docker}"
# SITE_ORIGIN 经 compose run -e 显式注入容器：sudo 会剥离命令前缀环境变量，
# compose 的 ${SITE_ORIGIN:?} 插值将回落到 deploy/.env 里的旧值
if $DOCKER compose --profile build run --rm -e SITE_ORIGIN="$SITE_ORIGIN" builder \
     bash /repo/scripts/rebuild-frontend.sh; then
  # builder 容器以 root 运行，产物属主改回当前宿主用户，
  # 否则其它路径（如宿主 cron 以 admin 跑）清理旧 release 时 rm 会 Permission denied
  sudo -n chown -R "$(id -un):$(id -gn)" "$APP_DIR/frontend" 2>/dev/null || true
  rm -f "$REQUEST_FILE"
  echo "watcher: rebuild ok $(date -u +%FT%TZ)"
else
  # 构建失败保留请求文件，下次 cron 自动重试
  echo "watcher: rebuild FAILED, keeping request for retry"
  exit 1
fi
