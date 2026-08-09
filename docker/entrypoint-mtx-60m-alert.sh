#!/bin/bash
set -euo pipefail

SESSION="${SESSION:?SESSION must be day or night}"
STATE_FILE="${MTX_60M_STATE_FILE:-/tmp/mtx-60m-bars.json}"

exec python scripts/run_mtx_60m_alert.py \
  --session "${SESSION}" \
  --state-file "${STATE_FILE}"
