#!/bin/sh
set -e

GCS_BUCKET="gs://bag-holder-data"
DATA_DIR="/app/data"
MIN_STOCK_FILES=1000

echo "[download-job] Fetching existing data from GCS..."
mkdir -p "${DATA_DIR}/stocks" "${DATA_DIR}/cache"

# Pull existing archive (ignore error on first run)
if gsutil cp "${GCS_BUCKET}/stocks.tar.gz" /tmp/stocks.tar.gz 2>/dev/null; then
  if tar xzf /tmp/stocks.tar.gz -C "${DATA_DIR}"; then
    echo "[download-job] Archive extracted successfully."
  else
    echo "[download-job] WARNING: tar extraction failed, starting fresh."
  fi
else
  echo "[download-job] No existing archive found, starting fresh."
fi

echo "[download-job] Downloading from ${DOWNLOAD_DATA_SOURCE:-fubon}..."
python main.py download

# Guard: only upload if stocks directory has enough files to be valid.
# This prevents overwriting the GCS archive with an empty/corrupt dataset
# (e.g. when tar extraction silently failed and download wrote nothing).
STOCK_COUNT=$(find "${DATA_DIR}/stocks" -name "*.csv" 2>/dev/null | wc -l | tr -d ' ')
echo "[download-job] Stock files in directory: ${STOCK_COUNT}"

if [ "${STOCK_COUNT}" -lt "${MIN_STOCK_FILES}" ]; then
  echo "[download-job] WARNING: only ${STOCK_COUNT} stock files found (threshold: ${MIN_STOCK_FILES})."
  echo "[download-job] Skipping GCS upload to preserve existing data."
else
  echo "[download-job] Uploading updated data to GCS (${STOCK_COUNT} files)..."
  tar czf /tmp/stocks.tar.gz -C "${DATA_DIR}" stocks cache
  gsutil cp /tmp/stocks.tar.gz "${GCS_BUCKET}/stocks.tar.gz"
  echo "[download-job] Upload complete."
fi

echo "[download-job] Syncing TAIFEX tick data..."
mkdir -p "${DATA_DIR}/taifex_tick"

# Pull existing taifex_tick archive
if gsutil cp "${GCS_BUCKET}/taifex_tick.tar.gz" /tmp/taifex_tick.tar.gz 2>/dev/null; then
  tar xzf /tmp/taifex_tick.tar.gz -C "${DATA_DIR}" 2>/dev/null || true
fi

# Download missing tick zips from TAIFEX (近 30 個交易日)
python scripts/download_taifex_tick.py --out "${DATA_DIR}/taifex_tick"

# Upload updated archive back to GCS
TICK_COUNT=$(find "${DATA_DIR}/taifex_tick" -name "Daily_*.zip" 2>/dev/null | wc -l | tr -d ' ')
echo "[download-job] TAIFEX tick files: ${TICK_COUNT}"
if [ "${TICK_COUNT}" -gt 0 ]; then
  tar czf /tmp/taifex_tick.tar.gz -C "${DATA_DIR}" taifex_tick
  gsutil cp /tmp/taifex_tick.tar.gz "${GCS_BUCKET}/taifex_tick.tar.gz"
  echo "[download-job] TAIFEX tick upload complete."
fi

echo "[download-job] Done."
