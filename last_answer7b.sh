#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
latest="$(ls -t runs/*.log 2>/dev/null | head -n 1 || true)"
[ -n "$latest" ] || { echo "No logs yet in $DIR/runs"; exit 1; }
awk '/^Final Answer:/{fa=$0} END{if (fa!="") print fa; else print "Final Answer: (not found yet)"}' "$latest"
