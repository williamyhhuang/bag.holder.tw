#!/bin/bash
# GCE startup-script for MTX auto trader (Container-Optimized OS)
#
# COS 的 /etc 不跨重開機保存，此腳本每次開機都會執行：
#   1. 設定 docker 對 Artifact Registry 的認證
#   2. 產生 launch.sh（pull :latest 後啟動 container，secret 在 container 內抓取）
#   3. 寫入 systemd service + timer（day 08:44 / night 14:59 台北時間，台灣無 DST 直接用 UTC）
#   4. catch-up dispatcher：若開機當下已在交易時段（如 Spot 搶占後被 keepalive 拉起），
#      立即補啟動對應 session（Python 端 _already_ended 防護為第二道保險）
set -euo pipefail

META="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
IMAGE=$(curl -s -H "Metadata-Flavor: Google" "${META}/mtx-image")

# COS 的 /root 唯讀，docker 認證設定改放 /var/lib/mtx/home
mkdir -p /var/lib/mtx/home
export HOME=/var/lib/mtx/home
docker-credential-gcr configure-docker --registries=asia-east1-docker.pkg.dev

# ── launcher：每次啟動前 pull 最新 image；APP_SECRETS 在 container 內用
#    image 自帶的 gcloud（走 metadata server 取 VM SA token）抓取，不落地 host ──
cat > /var/lib/mtx/launch.sh <<LAUNCH
#!/bin/bash
set -euo pipefail
export HOME=/var/lib/mtx/home
SESSION="\$1"
docker pull ${IMAGE}
docker image prune -f >/dev/null 2>&1 || true
exec docker run --rm --name "mtx-trader-\${SESSION}" \\
  --log-driver=gcplogs \\
  -e SESSION="\${SESSION}" \\
  -e APP_ENV=production \\
  -e PYTHONUNBUFFERED=1 \\
  --entrypoint /bin/bash ${IMAGE} -c \\
  'export APP_SECRETS="\$(gcloud secrets versions access latest --secret=APP_SECRETS)" && exec /entrypoint-mtx-trader.sh'
LAUNCH
chmod +x /var/lib/mtx/launch.sh

# ── systemd units ────────────────────────────────────────────────────────────
# Restart=on-failure：watchdog sys.exit(1) → 自動重啟（重啟時會重新 pull + seed bars）
#                     收盤正常結束 exit 0 → 不重啟
for S in day night; do
  cat > "/etc/systemd/system/mtx-trader-${S}.service" <<UNIT
[Unit]
Description=MTX auto trader (${S} session)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=-/usr/bin/docker rm -f mtx-trader-${S}
# COS 的 /var/lib 掛載 noexec，不能直接執行 script，需經由 bash
ExecStart=/bin/bash /var/lib/mtx/launch.sh ${S}
Restart=on-failure
RestartSec=60
UNIT
done

# 台北 08:44 = 00:44 UTC（日盤 08:45–13:30）
cat > /etc/systemd/system/mtx-trader-day.timer <<'UNIT'
[Unit]
Description=Start MTX day session (08:44 Asia/Taipei)

[Timer]
OnCalendar=Mon..Fri 00:44:00 UTC

[Install]
WantedBy=timers.target
UNIT

# 台北 14:59 = 06:59 UTC（夜盤 15:00–05:00+1）
cat > /etc/systemd/system/mtx-trader-night.timer <<'UNIT'
[Unit]
Description=Start MTX night session (14:59 Asia/Taipei)

[Timer]
OnCalendar=Mon..Fri 06:59:00 UTC

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now mtx-trader-day.timer mtx-trader-night.timer

# ── catch-up dispatcher：開機當下已在交易時段則立即補啟動對應 session ──────────
TPE_DOW=$(TZ=Asia/Taipei date +%u)   # 1=Mon .. 7=Sun
TPE_HM=$((10#$(TZ=Asia/Taipei date +%H%M)))

# 台期所交易時段（台北時間）：
#   日盤  Mon(1)–Fri(5)  08:45–13:30
#   夜盤  Mon(1)–Fri(5) 15:00 → 翌日 05:00（跨日段 Tue(2)–Sat(6) 00:00–05:00）
#   週日(7)整天 & 週六(6) 05:00 後 = CLOSED；週一凌晨也是 CLOSED（無週日夜盤）
if [ "${TPE_DOW}" -le 5 ] && [ "${TPE_HM}" -ge 844 ] && [ "${TPE_HM}" -lt 1331 ]; then
  systemctl start mtx-trader-day.service
elif { [ "${TPE_DOW}" -le 5 ] && [ "${TPE_HM}" -ge 1459 ]; } ||
     { [ "${TPE_DOW}" -ge 2 ] && [ "${TPE_DOW}" -le 6 ] && [ "${TPE_HM}" -lt 501 ]; }; then
  systemctl start mtx-trader-night.service
fi
