#!/bin/bash
# Docker entrypoint for MTX auto trader Cloud Run Job.
# SESSION env var controls the trading session: day | night | auto (default).
set -euo pipefail

SESSION="${SESSION:-auto}"
DRY_RUN_FLAG=""
if [ "${DRY_RUN:-false}" = "true" ]; then
  DRY_RUN_FLAG="--dry-run"
fi

echo "[entrypoint-mtx-trader] SESSION=${SESSION}  DRY_RUN=${DRY_RUN:-false}"

exec python scripts/run_mtx_trader.py \
  --session "${SESSION}" \
  ${DRY_RUN_FLAG}
