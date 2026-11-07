#!/usr/bin/env bash
# 一键启动本地开发环境：FastAPI 后端 + Vite 前端（含自动代理到所选后端端口）。
# 用法：
#   ./dev.sh
#   BACKEND_PORT=8001 FRONTEND_PORT=5174 ./dev.sh
#   BACKEND_RELOAD=1 ./dev.sh        # uvicorn --reload
# Ctrl+C 同时停止前后端。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_PORT_EXPLICIT="${BACKEND_PORT:-}"
FRONTEND_PORT_EXPLICIT="${FRONTEND_PORT:-}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

info() { printf '[dev] %s\n' "$*"; }
die() { printf '[dev] 错误：%s\n' "$*" >&2; exit 1; }

if [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  PY="$BACKEND_DIR/.venv/Scripts/python.exe"
elif [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  PY="$BACKEND_DIR/.venv/bin/python"
else
  die "找不到后端虚拟环境。先执行：cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt"
fi

command -v node >/dev/null 2>&1 || die "找不到 node（前端需要 Node.js）"
command -v curl >/dev/null 2>&1 || die "找不到 curl（用于健康检查）"
[ -f "$FRONTEND_DIR/node_modules/vite/bin/vite.js" ] || die "前端依赖未安装。先执行：cd frontend && npm install"

port_busy() {
  node -e '
    const s = require("net").connect(Number(process.argv[1]), "127.0.0.1")
    const done = (busy) => { s.destroy(); process.exit(busy ? 0 : 1) }
    s.on("connect", () => done(true))
    s.on("error", () => done(false))
    s.setTimeout(600, () => done(false))
  ' "$1" >/dev/null 2>&1
}

pick_port() {
  local p="$1"
  for ((i = 0; i < 20; i++)); do
    port_busy "$p" || { printf '%s' "$p"; return 0; }
    p=$((p + 1))
  done
  return 1
}

if port_busy "$BACKEND_PORT"; then
  [ -n "$BACKEND_PORT_EXPLICIT" ] && die "后端端口 $BACKEND_PORT 已被占用。换端口：BACKEND_PORT=8001 ./dev.sh"
  ALT="$(pick_port $((BACKEND_PORT + 1)))" || die "后端 8000 附近没有空闲端口"
  info "后端 $BACKEND_PORT 被占用，自动改用 $ALT"
  BACKEND_PORT="$ALT"
fi

if port_busy "$FRONTEND_PORT"; then
  [ -n "$FRONTEND_PORT_EXPLICIT" ] && die "前端端口 $FRONTEND_PORT 已被占用。换端口：FRONTEND_PORT=5174 ./dev.sh"
  ALT="$(pick_port $((FRONTEND_PORT + 1)))" || die "前端 5173 附近没有空闲端口"
  info "前端 $FRONTEND_PORT 被占用，自动改用 $ALT"
  FRONTEND_PORT="$ALT"
fi
RELOAD_ARGS=()
[ "${BACKEND_RELOAD:-0}" = "1" ] && RELOAD_ARGS=(--reload)

pids=()
stopping=0
cleanup() {
  [ "$stopping" = 1 ] && return
  stopping=1
  trap - EXIT INT TERM
  info "正在停止前后端…"
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] || continue
    kill -0 "$pid" 2>/dev/null || continue
    case "${OSTYPE:-}" in
      msys*|cygwin*|win32*)
        taskkill //PID "$pid" //T //F >/dev/null 2>&1 || kill "$pid" 2>/dev/null
        ;;
      *)
        kill "$pid" 2>/dev/null
        ;;
    esac
  done
  wait 2>/dev/null
  info "已停止"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

info "后端 :$BACKEND_PORT  前端 :$FRONTEND_PORT"
(
  cd "$BACKEND_DIR" || exit 1
  exec "$PY" -m uvicorn app.main:app --port "$BACKEND_PORT" "${RELOAD_ARGS[@]}"
) &
BACKEND_PID=$!
pids+=("$BACKEND_PID")

ready=0
for ((i = 0; i < 40; i++)); do
  curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/v1/site-config" >/dev/null 2>&1 && { ready=1; break; }
  kill -0 "$BACKEND_PID" 2>/dev/null || break
  sleep 0.5
done
[ "$ready" = 1 ] || die "后端 20 秒内未就绪，检查上面的日志（.env、数据库或依赖）"
info "后端就绪"

(
  cd "$FRONTEND_DIR" || exit 1
  exec env \
    DEV_PROXY_TARGET="http://127.0.0.1:$BACKEND_PORT" \
    VITE_STATIC=false \
    node "$FRONTEND_DIR/node_modules/vite/bin/vite.js" \
      --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) &
FRONTEND_PID=$!
pids+=("$FRONTEND_PID")

fready=0
for ((i = 0; i < 40; i++)); do
  curl -fsS -o /dev/null "http://127.0.0.1:$FRONTEND_PORT/" 2>/dev/null && { fready=1; break; }
  kill -0 "$FRONTEND_PID" 2>/dev/null || break
  sleep 0.5
done
[ "$fready" = 1 ] || die "前端 20 秒内未就绪，检查上面的日志"

cat <<EOF

  前端   http://127.0.0.1:$FRONTEND_PORT
  后台   http://127.0.0.1:$FRONTEND_PORT/admin
  接口   http://127.0.0.1:$BACKEND_PORT/api/v1

  Ctrl+C 同时停止前后端
EOF

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
info "有进程退出，正在停止另一个…"
exit 0