#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

QUESTION="${1:-}"
[ -z "$QUESTION" ] && { echo "Usage: $0 \"YOUR QUESTION\""; exit 1; }

CHAINS="${CHAINS:-10}"
MAJ_MIN="${MAJ_MIN:-0.5}"   # e.g., 0.5 requires simple majority
MAX_ROUNDS="${MAX_ROUNDS:-3}"

SESSION_TOOL="$DIR/mjthinking_session.py"
SESSION_ID="${MJTHINKING_SESSION_ID:-$(date -u +"mjthinking_%Y%m%dT%H%M%SZ")}" 
SESSION_BASE="$DIR/runs/$SESSION_ID"
RAW_DIR="$SESSION_BASE/raw"
mkdir -p "$RAW_DIR"
export MJTHINKING_SESSION_DIR="$RAW_DIR"

SESSION_DRIVER="mjthinking.sh"
python3 "$SESSION_TOOL" init \
  --session "$SESSION_ID" \
  --question "$QUESTION" \
  --driver "$SESSION_DRIVER" \
  --param "CHAINS=$CHAINS" \
  --param "MAJ_MIN=$MAJ_MIN" \
  --param "MAX_ROUNDS=$MAX_ROUNDS"

SESSION_STATUS="running"
final_answer=""
final_conf=""

cleanup_session() {
  local status="$1"
  local answer="${2:-${final_answer:-}}"
  local confidence="${3:-${final_conf:-}}"
  python3 "$SESSION_TOOL" finalize \
    --session "$SESSION_ID" \
    --answer "${answer}" \
    --confidence "${confidence}" \
    --model "" \
    --status "$status" || true
}

trap 'exit_code=$?; if [ "$SESSION_STATUS" != "completed" ]; then cleanup_session "failed"; fi; exit $exit_code' EXIT

format_duration() {
  local total=${1:-0}
  if (( total < 0 )); then total=$(( -total )); fi
  local hours=$(( total / 3600 ))
  local minutes=$(( (total % 3600) / 60 ))
  local seconds=$(( total % 60 ))
  local parts=()
  if (( hours > 0 )); then parts+=("${hours}h"); fi
  if (( minutes > 0 )); then parts+=("${minutes}m"); fi
  parts+=("${seconds}s")
  printf '%s' "${parts[*]}"
}

progress_bar() {
  local current=${1:-0}
  local total=${2:-1}
  local width=${3:-20}
  if (( total <= 0 )); then total=1; fi
  local percent=$(( current * 100 / total ))
  if (( percent > 100 )); then percent=100; fi
  local filled=$(( percent * width / 100 ))
  if (( filled > width )); then filled=$width; fi
  local empty=$(( width - filled ))
  printf '['
  printf '#%.0s' $(seq 1 $filled)
  printf '-%.0s' $(seq 1 $empty)
  printf '] %3d%%' "$percent"
}

round=1
curr_chains="$CHAINS"
START_TS=$(date +%s)

while : ; do
  echo
  echo "[*] Round $round — running $curr_chains chains…"
  "$DIR/mjthinking_core.sh" "$QUESTION" "$curr_chains"

  # Load summary from core runner
  source "$DIR/runs/summary.env" || { echo "[!] No summary found"; exit 2; }
  FA="$FINAL_ANSWER"; FC="${FINAL_COUNT:-0}"; TOT="${TOTAL_CHAINS:-$curr_chains}"

  echo "[*] Majority: $FC / $TOT"
  maj_req=$(python3 - <<PY
tot=$TOT
mm=float("$MAJ_MIN")
req=int(mm*tot+0.999999)
print(req)
PY
)
  # Referee verification
  echo "[*] Verifying with referee…"
  RVER="$("$DIR/referee.sh" "$QUESTION" "$FA" | grep '^VERDICT=' | cut -d= -f2 || echo UNKNOWN)"
  echo "[*] Referee verdict: $RVER"

  # Optional numeric auto-check (fast arithmetic only)
  NVER="$(python3 "$DIR/arith_eval.py" "$QUESTION" "$FA" 2>/dev/null || true)"
  [ -z "$NVER" ] && NVER="UNKNOWN"
  echo "[*] Numeric check: $NVER"

  pass_majority=$([ "$FC" -ge "$maj_req" ] && echo YES || echo NO)
  pass_ref="$([ "$RVER" = "PASS" ] && echo YES || echo NO)"
  pass_numeric="$([ "$NVER" = "PASS" ] && echo YES || echo NO)"

  now=$(date +%s)
  elapsed=$(( now - START_TS ))
  bar=$(progress_bar "$round" "$MAX_ROUNDS")
  if (( round > 0 )); then
    per_round=$(( elapsed / round ))
    remaining_rounds=$(( MAX_ROUNDS - round ))
    if (( remaining_rounds > 0 && per_round > 0 )); then
      eta_seconds=$(( remaining_rounds * per_round ))
      eta_str=$(format_duration "$eta_seconds")
    else
      eta_str="0s"
    fi
  else
    eta_str="--"
  fi
  elapsed_str=$(format_duration "$elapsed")
  echo "[progress] $bar | elapsed=$elapsed_str | eta~$eta_str"

  if [ "$pass_majority" = "YES" ] && [ "$pass_ref" = "YES" ]; then
    echo
    echo "================== MJThinking RESULT =================="
    echo "Final Answer: $FA"
    echo "(Majority $FC/$TOT • Referee PASS • Numeric $NVER)"
    echo "All traces under: $DIR/runs/"
    echo "====================================================="
    exit 0
  fi

  if [ "$round" -ge "$MAX_ROUNDS" ]; then
    echo
    echo "================== MJThinking (BEST EFFORT) ========="
    echo "Final Answer: $FA"
    echo "(Majority $FC/$TOT • Referee $RVER • Numeric $NVER)"
    echo "Reached MAX_ROUNDS=$MAX_ROUNDS. Inspect runs/ for details."
    echo "====================================================="
    exit 0
  fi

  # Escalate: double chains, next round
  round=$((round+1))
  curr_chains=$((curr_chains*2))
done
