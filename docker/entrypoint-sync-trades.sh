#!/bin/sh
set -e

echo "[sync-trades-job] 查詢 Fubon 今日成交記錄並同步至 Google Sheets..."
python main.py sync-trades

echo "[sync-trades-job] Done."
