#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ $# -eq 0 ]; then
  echo "Usage: mjthinking_run7b_bg.sh \"YOUR PROMPT\""
  exit 1
fi
PROMPT="$*"

# Defaults (override by exporting env vars inline)
TIME_BUDGET="${TIME_BUDGET:-1800}"
BATCH="${BATCH:-12}"
PREDICT="${PREDICT:-1600}"
CTX="${CTX:-8192}"
MODE="${MODE:-HYBRID}"
PLANS="${PLANS:-3}"
EXPAND="${EXPAND:-2}"

ts="$(date +"%Y%m%d_%H%M%S")"
log="runs/${ts}.log"
pidf="runs/${ts}.pid"

echo "[*] Starting MJThinking 7B-only run..."
echo "    Log:  $DIR/$log"
echo "    PID:  will be written to $DIR/$pidf"
nohup env TIME_BUDGET="$TIME_BUDGET" BATCH="$BATCH" PREDICT="$PREDICT" \
  CTX="$CTX" MODE="$MODE" PLANS="$PLANS" EXPAND="$EXPAND" \
  python3 mjthinking_ultra7b.py "$PROMPT" > "$log" 2>&1 & echo $! > "$pidf"
echo "[OK] Running in background."
echo "Tail logs: tail -f \"$DIR/$log\""
