#!/bin/sh
set -e

GCS_BUCKET="gs://bag-holder-data"
DATA_DIR="/app/data"

echo "[ma-cross-job] Fetching data from GCS..."
mkdir -p "${DATA_DIR}/stocks" "${DATA_DIR}/cache"

gsutil cp "${GCS_BUCKET}/stocks.tar.gz" /tmp/stocks.tar.gz
tar xzf /tmp/stocks.tar.gz -C "${DATA_DIR}"

# 細產業對照快取（產業價值鏈平台，7 天 TTL）跨次執行保存於 GCS，避免每天重抓
gsutil cp "${GCS_BUCKET}/sub_industries.json" "${DATA_DIR}/cache/sub_industries.json" 2>/dev/null || \
  echo "[ma-cross-job] No sub-industry cache in GCS, will fetch from TPEx."

echo "[ma-cross-job] Running ma-cross..."
python main.py ma-cross --send-telegram --require-today

if [ -f "${DATA_DIR}/cache/sub_industries.json" ]; then
  gsutil cp "${DATA_DIR}/cache/sub_industries.json" "${GCS_BUCKET}/sub_industries.json" || true
fi

echo "[ma-cross-job] Done."
