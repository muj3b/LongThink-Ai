#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
TIME_BUDGET="${TIME_BUDGET:-1800}" \
BATCH="${BATCH:-12}" \
PREDICT="${PREDICT:-1600}" \
CTX="${CTX:-8192}" \
MODE="${MODE:-HYBRID}" \
python3 mjthinking_ultra7b.py "$@"
