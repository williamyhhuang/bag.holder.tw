#!/bin/bash
set -euo pipefail

SESSION="${SESSION:?SESSION must be day or night}"
INTERVAL="${INTERVAL:-60}"
STATE_FILE="${MTX_MA_STATE_FILE:-${MTX_60M_STATE_FILE:-/tmp/mtx-${INTERVAL}m-bars.json}}"

exec python scripts/run_mtx_60m_alert.py \
  --session "${SESSION}" \
  --interval "${INTERVAL}" \
  --state-file "${STATE_FILE}"
