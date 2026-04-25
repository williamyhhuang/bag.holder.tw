#!/bin/sh
# entrypoint-webhook.sh — 啟動 Telegram Webhook Cloud Run Service
#
# 流程:
#   1. 向 Telegram 註冊 webhook URL
#   2. 啟動 uvicorn (FastAPI) 監聽 $PORT
#
# 環境變數 (從 Cloud Run --set-secrets 注入 APP_SECRETS JSON，
# config/settings.py 在 import 時自動展開):
#   TELEGRAM_BOT_TOKEN       必填
#   TELEGRAM_WEBHOOK_URL     必填 (e.g. https://<service-url>)
#   TELEGRAM_WEBHOOK_SECRET  選填，若設定則驗證 Telegram 請求

set -e

PORT="${PORT:-8080}"

# 等 settings.py 展開 APP_SECRETS 後才能讀值，
# 所以用 python 取得實際 token / url / secret
eval "$(python3 - <<'EOF'
import sys
sys.path.insert(0, '/app')
from config.settings import settings

token = settings.telegram.bot_token
url = (settings.telegram.webhook_url or '').rstrip('/')
secret = settings.telegram.webhook_secret or ''

print(f'BOT_TOKEN={token!r}')
print(f'WEBHOOK_URL={url!r}')
print(f'WEBHOOK_SECRET={secret!r}')
EOF
)"

if [ -z "${BOT_TOKEN}" ] || [ "${BOT_TOKEN}" = "dummy_token" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN is not configured"
    exit 1
fi

if [ -z "${WEBHOOK_URL}" ]; then
    echo "ERROR: TELEGRAM_WEBHOOK_URL is not configured"
    exit 1
fi

FULL_WEBHOOK="${WEBHOOK_URL}/webhook"
echo "[webhook] Registering Telegram webhook → ${FULL_WEBHOOK}"

if [ -n "${WEBHOOK_SECRET}" ]; then
    curl -sf -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
        -d "url=${FULL_WEBHOOK}" \
        -d "secret_token=${WEBHOOK_SECRET}" \
        -d "drop_pending_updates=true" \
        || echo "WARNING: webhook registration failed, continuing..."
else
    curl -sf -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
        -d "url=${FULL_WEBHOOK}" \
        -d "drop_pending_updates=true" \
        || echo "WARNING: webhook registration failed, continuing..."
fi

echo "[webhook] Starting uvicorn on port ${PORT}..."
exec uvicorn src.interfaces.api.webhook_app:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1
