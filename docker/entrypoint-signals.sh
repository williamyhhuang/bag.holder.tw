#!/bin/sh
set -e

GCS_BUCKET="gs://bag-holder-data"
DATA_DIR="/app/data"

echo "[signals-job] Fetching data from GCS..."
mkdir -p "${DATA_DIR}/stocks" "${DATA_DIR}/cache" "${DATA_DIR}/signals_log"

gsutil cp "${GCS_BUCKET}/stocks.tar.gz" /tmp/stocks.tar.gz
tar xzf /tmp/stocks.tar.gz -C "${DATA_DIR}"

echo "[signals-job] Running signals..."
python main.py signals --send-telegram

echo "[signals-job] Done."
