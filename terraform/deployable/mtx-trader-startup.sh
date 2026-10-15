#!/bin/bash
# GCE startup-script for MTX 60K / 5K Telegram alert (Container-Optimized OS)
#
# COS 的 /etc 不跨重開機保存，此腳本每次開機都會執行：
#   1. 設定 docker 對 Artifact Registry 的認證
#   2. 產生 60K / 5K 警示的 container launcher（secret 在 container 內抓取）
#   3. 寫入日／夜盤 60K、5K 警示的 systemd service + timer
#
# 原本的 MTX 模擬下單 mtx-trader-day/night 已停用，不在此 VM 自動啟動。
set -euo pipefail

META="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
IMAGE=$(curl -s -H "Metadata-Flavor: Google" "${META}/mtx-image")

# COS 的 /root 唯讀，docker 認證與跨排程 60K 狀態放在持久化的 /var/lib
mkdir -p /var/lib/mtx/home /var/lib/mtx/state
export HOME=/var/lib/mtx/home
docker-credential-gcr configure-docker --registries=asia-east1-docker.pkg.dev

# ── 分 K 警示 launcher：使用同一個 image，狀態掛載到 VM 持久磁碟 ─────────────
# 用法：launch-ma-alert.sh <day|night> <60|5>
cat > /var/lib/mtx/launch-ma-alert.sh <<LAUNCH
#!/bin/bash
set -euo pipefail
export HOME=/var/lib/mtx/home
SESSION="\$1"
INTERVAL="\${2:-60}"
if ! docker pull ${IMAGE}; then
  echo "WARNING: image pull failed; using cached image if available" >&2
fi
# 每次 pull :latest 都會留下未標記的舊 image，不清理會塞滿 VM 磁碟導致 pull 失敗
docker image prune -f >/dev/null 2>&1 || true
# MTX_60M_STATE_FILE 供不認得 INTERVAL 的舊 image 使用：舊 image 一律跑 60K 邏輯，
# 固定指向 60K 狀態檔（同一根 K 已通知的 marker 會擋掉重複發送）
# 60K 與 5K 同時觸發時排隊執行，避免同一富邦帳號並行登入（lock 由 fd 9 持有至 container 結束）
exec 9>/var/lib/mtx/alert.lock
if command -v flock >/dev/null; then
  flock -w 120 9 || echo "WARNING: alert lock wait timed out" >&2
fi
exec docker run --rm --name "mtx-\${INTERVAL}m-alert" \\
  --log-driver=gcplogs \\
  -e SESSION="\${SESSION}" \\
  -e INTERVAL="\${INTERVAL}" \\
  -e MTX_MA_STATE_FILE=/var/lib/mtx/state/\${INTERVAL}m-bars.json \\
  -e MTX_60M_STATE_FILE=/var/lib/mtx/state/60m-bars.json \\
  -e APP_ENV=production \\
  -e PYTHONUNBUFFERED=1 \\
  -v /var/lib/mtx/state:/var/lib/mtx/state \\
  --entrypoint /bin/bash ${IMAGE} -c \\
  'export APP_SECRETS="\$(gcloud secrets versions access latest --secret=APP_SECRETS)" && exec /entrypoint-mtx-60m-alert.sh'
LAUNCH
chmod +x /var/lib/mtx/launch-ma-alert.sh
rm -f /var/lib/mtx/launch-60m-alert.sh

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
ExecStart=/bin/bash /var/lib/mtx/launch-ma-alert.sh %i 60
TimeoutStartSec=300
UNIT

# 5K 警示：每根 5K 收完後 20 秒檢查，只在多排／空排剛成立或轉向時通知。
cat > /etc/systemd/system/mtx-5m-alert@.service <<'UNIT'
[Unit]
Description=MTX 5-minute MA alert (%i session)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=-/usr/bin/docker rm -f mtx-5m-alert
ExecStart=/bin/bash /var/lib/mtx/launch-ma-alert.sh %i 5
TimeoutStartSec=240
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

# 日盤 5K：台北 08:50–13:45 每 5 分鐘（K 棒收完後 20 秒）。
# 換算 UTC：週一至週五 00:50–05:45。
cat > /etc/systemd/system/mtx-5m-alert-day.timer <<'UNIT'
[Unit]
Description=Check MTX day-session 5-minute MA alert

[Timer]
Unit=mtx-5m-alert@day.service
OnCalendar=Mon..Fri 00:50,55:20
OnCalendar=Mon..Fri 01..04:00/5:20
OnCalendar=Mon..Fri 05:00,05,10,15,20,25,30,35,40,45:20
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT

# 夜盤 5K：台北 15:05–翌日 05:00 每 5 分鐘（K 棒收完後 20 秒）。
# 換算 UTC：週一至週五 07:05–21:00。
cat > /etc/systemd/system/mtx-5m-alert-night.timer <<'UNIT'
[Unit]
Description=Check MTX night-session 5-minute MA alert

[Timer]
Unit=mtx-5m-alert@night.service
OnCalendar=Mon..Fri 07:05/5:20
OnCalendar=Mon..Fri 08..20:00/5:20
OnCalendar=Mon..Fri 21:00:20
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now \
  mtx-60m-alert-day.timer \
  mtx-60m-alert-night.timer \
  mtx-5m-alert-day.timer \
  mtx-5m-alert-night.timer
