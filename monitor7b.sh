#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
latest="$(ls -t runs/*.log 2>/dev/null | head -n 1 || true)"
[ -n "$latest" ] || { echo "No logs yet in $DIR/runs"; exit 1; }
echo "[*] Tailing $DIR/$latest"
tail -f "$latest"
