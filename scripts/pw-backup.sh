#!/usr/bin/env bash
# 每日备份 —— 覆盖同一台机器上的三套服务：personal-web（主站）、personal-mail（邮件镜像）、
# lexi（词书站 /home/admin/Dictionary）。说明见 docs/deployment.md §8-A
#
# 三条硬规矩（都是踩出来的）：
# 1) 宿主机没有 sqlite3 CLI，SQLite 一律借容器里的 python 走 backup API 取一致快照；
#    绝不直接 tar 正在写的 app.db-wal（旧机上 WAL 里压着 4MB 未合并数据）。
# 2) 快照必须过 integrity_check，不过就非零退出 —— 宁可今天没备份，也不能备份一个开不了的库。
# 3) 卷里有不可再生的东西（personal-mail 的 master.key、caddy 的 LE 证书与 ACME 账户密钥），
#    必须一起备；但绝不要为此去 docker volume prune。
#
# 诚实说明它防什么：备份落在同一块盘上，防的是误删/库损坏/发布出事，不防磁盘或实例丢失
# —— 后者靠云快照。异地副本另说。
set -euo pipefail

PW_HOME="${PW_HOME:-$HOME/personal-web}"
LEXI_HOME="${LEXI_HOME:-$HOME/Dictionary}"
OUT="${PW_BACKUP_DIR:-$HOME/pw-backups}"
KEEP_DAYS="${PW_BACKUP_KEEP_DAYS:-14}"
TS="$(date +%F)"
COMPOSE="$PW_HOME/deploy/docker-compose.yml"
VOLROOT=/var/lib/docker/volumes

log() { echo "[pw-backup] $(date '+%F %T') $*"; }

mkdir -p "$OUT"
chmod 700 "$OUT"
STAGE="$(mktemp -d "$HOME/.pwbak.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

log "start ts=$TS pw=$PW_HOME out=$OUT keep=${KEEP_DAYS}d"

if ! sudo -n docker compose -f "$COMPOSE" ps -q backend | grep -q .; then
  log "FATAL: backend 容器没在跑，取不了快照"
  exit 1
fi

# 1. 主站库一致快照
if ! sudo -n docker compose -f "$COMPOSE" exec -T backend python - /app/data/app.db "/tmp/pw-$TS.db" <<'PY'
import sqlite3, sys
s = sqlite3.connect(sys.argv[1])
d = sqlite3.connect(sys.argv[2])
s.backup(d)
d.commit()
ok = d.execute("PRAGMA integrity_check").fetchone()[0]
n = d.execute("SELECT COUNT(*) FROM contents").fetchone()[0]
u = d.execute("SELECT COUNT(*) FROM users").fetchone()[0]
print("main db: integrity=%s contents=%s users=%s" % (ok, n, u))
sys.exit(0 if ok == "ok" else 2)
PY
then
  log "FATAL: 主站库快照失败或 integrity_check 未通过，本次不产出备份"
  exit 1
fi
sudo -n docker cp "deploy-backend-1:/tmp/pw-$TS.db" "$STAGE/app-$TS.db"
sudo -n docker exec deploy-backend-1 rm -f "/tmp/pw-$TS.db"

# 2. personal-mail 库一致快照（同为 WAL 模式，容器名由 compose 的 container_name 固定）
if ! sudo -n docker exec -i personal-mail python - /data/app.db "/tmp/pm-$TS.db" <<'PY'
import sqlite3, sys
s = sqlite3.connect(sys.argv[1])
d = sqlite3.connect(sys.argv[2])
s.backup(d)
d.commit()
ok = d.execute("PRAGMA integrity_check").fetchone()[0]
m = d.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
print("mail db: integrity=%s messages=%s" % (ok, m))
sys.exit(0 if ok == "ok" else 2)
PY
then
  log "FATAL: personal-mail 库快照失败或 integrity_check 未通过"
  exit 1
fi
sudo -n docker cp "personal-mail:/tmp/pm-$TS.db" "$STAGE/pm-app-$TS.db"
sudo -n docker exec personal-mail rm -f "/tmp/pm-$TS.db"

# 3. lexi 词书站（同机第三个服务）。它的主库文件只有 4KB、2.5MB 数据全压在 -wal 里，
#    直接 tar 主库会备到一个空库 —— 必须走 backup API。容器没在跑时只告警不失败：
#    lexi 是独立项目，停机不该让主站备份拿不到退出码。
if sudo -n docker ps --format '{{.Names}}' | grep -qx lexi-api; then
  if ! sudo -n docker exec -i lexi-api python - /app/data/lexi.db "/tmp/lexi-$TS.db" <<'PY'
import sqlite3, sys
s = sqlite3.connect(sys.argv[1])
d = sqlite3.connect(sys.argv[2])
s.backup(d)
d.commit()
ok = d.execute("PRAGMA integrity_check").fetchone()[0]
tabs = [r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
print("lexi db: integrity=%s tables=%d" % (ok, len(tabs)))
for t in sorted(tabs):
    print("   %-26s %s" % (t, d.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]))
sys.exit(0 if ok == "ok" else 2)
PY
  then
    log "FATAL: lexi 库快照失败或 integrity_check 未通过"
    exit 1
  fi
  sudo -n docker cp "lexi-api:/tmp/lexi-$TS.db" "$STAGE/lexi-$TS.db"
  sudo -n docker exec lexi-api rm -f "/tmp/lexi-$TS.db"
  # 单独打成嵌套包：lexi 也有 backend/data 与 backend/.env，与主站同名，直接放进外层会撞成员路径。
  # 必须 sudo：里面的 .admin-password 是 root 0600，以 admin 跑 tar 会 Permission denied 并让整次备份失败。
  sudo -n tar czf "$STAGE/lexi-$TS.tar.gz" -C "$LEXI_HOME" backend/data backend/.env
  sudo -n chmod 644 "$STAGE/lexi-$TS.tar.gz"   # 外层 tar 以 admin 读它
  log "lexi 已纳入：快照 + $(du -h "$STAGE/lexi-$TS.tar.gz" | cut -f1) 嵌套包（含 .admin-password 与 .env）"
else
  log "warn: lexi-api 容器没在跑，本次跳过 lexi（词书站）备份"
fi

# 4. 卷：库以外的正文/附件/密钥/证书。卷里的 app.db 可能是写了一半的，上面已有干净快照兜底
sudo -n tar cf "$STAGE/volumes-$TS.tar" -C "$VOLROOT" \
  personal-mail_pm-data/_data deploy_caddy_data/_data deploy_caddy_config/_data

# 5. crontab 原文（不在任何卷里，重装即丢）
crontab -l > "$STAGE/crontab-$TS.txt" 2>/dev/null || echo "(no crontab for $(id -un))" > "$STAGE/crontab-$TS.txt"

# 6. 打成一个包：三套数据 + 配置 + 干净快照 + 卷 + crontab + SSH
#    lexi 的两个成员只在容器在跑时存在，缺了就不能写进成员表（tar 报错会整次备份失败）
STAGE_MEMBERS=("app-$TS.db" "pm-app-$TS.db" "volumes-$TS.tar" "crontab-$TS.txt")
if [ -e "$STAGE/lexi-$TS.db" ]; then STAGE_MEMBERS+=("lexi-$TS.db"); fi
if [ -e "$STAGE/lexi-$TS.tar.gz" ]; then STAGE_MEMBERS+=("lexi-$TS.tar.gz"); fi
tar czf "$OUT/pw-$TS.tar.gz" \
  -C "$PW_HOME" backend/data backend/.env deploy/.env \
  -C "$HOME/personal-mail" secrets \
  -C "$HOME/.ssh" authorized_keys id_ed25519 id_ed25519.pub \
  -C "$STAGE" "${STAGE_MEMBERS[@]}"
chmod 600 "$OUT/pw-$TS.tar.gz"

# 7. 产出自检：成员清单 + 校验和
tar -tzf "$OUT/pw-$TS.tar.gz" > "$OUT/pw-$TS.list"
( cd "$OUT" && sha256sum "pw-$TS.tar.gz" > "pw-$TS.sha256" && sha256sum -c "pw-$TS.sha256" >/dev/null )

# 8. 轮换
find "$OUT" -maxdepth 1 -name 'pw-*' -mtime "+$KEEP_DAYS" -delete

SIZE=$(du -h "$OUT/pw-$TS.tar.gz" | cut -f1)
COUNT=$(wc -l < "$OUT/pw-$TS.list")
log "ok ts=$TS size=$SIZE members=$COUNT files_kept=$(ls "$OUT" | grep -c '^pw-.*\.tar\.gz$')"
