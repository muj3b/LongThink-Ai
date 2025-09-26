#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
pidf="$(ls -t runs/*.pid 2>/dev/null | head -n 1 || true)"
if [ -z "$pidf" ]; then
  echo "No PID file found; attempting to kill by name…"
  pkill -f mjthinking_ultra7b.py || true
  exit 0
fi
pid="$(cat "$pidf" 2>/dev/null || echo)"
[ -n "$pid" ] && kill "$pid" 2>/dev/null || true
echo "[OK] Stopped PID $pid"
