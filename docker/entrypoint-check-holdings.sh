#!/bin/sh
set -e

GCS_BUCKET="gs://bag-holder-data"
DATA_DIR="/app/data"

echo "[check-holdings-job] Fetching data from GCS..."
mkdir -p "${DATA_DIR}/stocks" "${DATA_DIR}/cache"

gsutil cp "${GCS_BUCKET}/stocks.tar.gz" /tmp/stocks.tar.gz
tar xzf /tmp/stocks.tar.gz -C "${DATA_DIR}"

echo "[check-holdings-job] Running holdings sell check..."
python main.py check-holdings --send-telegram

echo "[check-holdings-job] Done."
