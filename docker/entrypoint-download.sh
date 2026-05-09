#!/bin/sh
set -e

GCS_BUCKET="gs://bag-holder-data"
DATA_DIR="/app/data"

echo "[download-job] Fetching existing data from GCS..."
mkdir -p "${DATA_DIR}/stocks" "${DATA_DIR}/cache"

# Pull existing archive (ignore error on first run)
gsutil cp "${GCS_BUCKET}/stocks.tar.gz" /tmp/stocks.tar.gz 2>/dev/null && \
  tar xzf /tmp/stocks.tar.gz -C "${DATA_DIR}" || \
  echo "[download-job] No existing archive found, starting fresh."

echo "[download-job] Downloading from ${DOWNLOAD_DATA_SOURCE:-fubon}..."
python main.py download

echo "[download-job] Uploading updated data to GCS..."
tar czf /tmp/stocks.tar.gz -C "${DATA_DIR}" stocks cache
gsutil cp /tmp/stocks.tar.gz "${GCS_BUCKET}/stocks.tar.gz"

echo "[download-job] Done."
