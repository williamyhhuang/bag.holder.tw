#!/bin/bash
# GCE startup-script for MTX 60K Telegram alert (Container-Optimized OS)
#
# COS 的 /etc 不跨重開機保存，此腳本每次開機都會執行：
#   1. 設定 docker 對 Artifact Registry 的認證
#   2. 產生 60K 警示的 container launcher（secret 在 container 內抓取）
#   3. 寫入日／夜盤 60K 警示的 systemd service + timer
#
# 原本的 MTX 模擬下單 mtx-trader-day/night 已停用，不在此 VM 自動啟動。
set -euo pipefail

META="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
IMAGE=$(curl -s -H "Metadata-Flavor: Google" "${META}/mtx-image")

# COS 的 /root 唯讀，docker 認證與跨排程 60K 狀態放在持久化的 /var/lib
mkdir -p /var/lib/mtx/home /var/lib/mtx/state
export HOME=/var/lib/mtx/home
docker-credential-gcr configure-docker --registries=asia-east1-docker.pkg.dev

# ── 60K 警示 launcher：使用同一個 image，狀態掛載到 VM 持久磁碟 ─────────────
cat > /var/lib/mtx/launch-60m-alert.sh <<LAUNCH
#!/bin/bash
set -euo pipefail
export HOME=/var/lib/mtx/home
SESSION="\$1"
if ! docker pull ${IMAGE}; then
  echo "WARNING: image pull failed; using cached image if available" >&2
fi
exec docker run --rm --name "mtx-60m-alert" \\
  --log-driver=gcplogs \\
  -e SESSION="\${SESSION}" \\
  -e MTX_60M_STATE_FILE=/var/lib/mtx/state/60m-bars.json \\
  -e APP_ENV=production \\
  -e PYTHONUNBUFFERED=1 \\
  -v /var/lib/mtx/state:/var/lib/mtx/state \\
  --entrypoint /bin/bash ${IMAGE} -c \\
  'export APP_SECRETS="\$(gcloud secrets versions access latest --secret=APP_SECRETS)" && exec /entrypoint-mtx-60m-alert.sh'
LAUNCH
chmod +x /var/lib/mtx/launch-60m-alert.sh

# ── systemd units ────────────────────────────────────────────────────────────
# 清除舊版模擬交易 unit，避免 metadata 更新或重開機後再次啟動下單程式。
systemctl disable --now mtx-trader-day.timer mtx-trader-night.timer 2>/dev/null || true
systemctl stop mtx-trader-day.service mtx-trader-night.service 2>/dev/null || true
rm -f \
  /etc/systemd/system/mtx-trader-day.timer \
  /etc/systemd/system/mtx-trader-night.timer \
  /etc/systemd/system/mtx-trader-day.service \
  /etc/systemd/system/mtx-trader-night.service
docker rm -f mtx-trader-day mtx-trader-night 2>/dev/null || true

# 60K 警示為短任務，由 day/night timer 傳入 session。
cat > /etc/systemd/system/mtx-60m-alert@.service <<'UNIT'
[Unit]
Description=MTX 60-minute MA alert (%i session)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=-/usr/bin/docker rm -f mtx-60m-alert
ExecStart=/bin/bash /var/lib/mtx/launch-60m-alert.sh %i
TimeoutStartSec=300
UNIT

# 日盤 60K：台北 09:46 / 10:46 / 11:46 / 12:46，最後縮短 K 於 13:31。
# 換算 UTC：週一至週五 01:46 / 02:46 / 03:46 / 04:46 / 05:31。
cat > /etc/systemd/system/mtx-60m-alert-day.timer <<'UNIT'
[Unit]
Description=Check MTX day-session 60-minute MA alert

[Timer]
Unit=mtx-60m-alert@day.service
OnCalendar=Mon..Fri 01:46:00 UTC
OnCalendar=Mon..Fri 02:46:00 UTC
OnCalendar=Mon..Fri 03:46:00 UTC
OnCalendar=Mon..Fri 04:46:00 UTC
OnCalendar=Mon..Fri 05:31:00 UTC
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT

# 夜盤 60K：台北週一至週五 16:01 起，每小時至翌日 05:01。
# 全部換算為同一個 UTC 交易日的 08:01–21:01。
cat > /etc/systemd/system/mtx-60m-alert-night.timer <<'UNIT'
[Unit]
Description=Check MTX night-session 60-minute MA alert

[Timer]
Unit=mtx-60m-alert@night.service
OnCalendar=Mon..Fri 08:01:00 UTC
OnCalendar=Mon..Fri 09:01:00 UTC
OnCalendar=Mon..Fri 10:01:00 UTC
OnCalendar=Mon..Fri 11:01:00 UTC
OnCalendar=Mon..Fri 12:01:00 UTC
OnCalendar=Mon..Fri 13:01:00 UTC
OnCalendar=Mon..Fri 14:01:00 UTC
OnCalendar=Mon..Fri 15:01:00 UTC
OnCalendar=Mon..Fri 16:01:00 UTC
OnCalendar=Mon..Fri 17:01:00 UTC
OnCalendar=Mon..Fri 18:01:00 UTC
OnCalendar=Mon..Fri 19:01:00 UTC
OnCalendar=Mon..Fri 20:01:00 UTC
OnCalendar=Mon..Fri 21:01:00 UTC
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now \
  mtx-60m-alert-day.timer \
  mtx-60m-alert-night.timer
