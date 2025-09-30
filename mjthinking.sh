#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Argument Parsing ---
QUESTION=""
RESUME_SESSION=""
# Simple loop to parse arguments. Supports --resume <id> and positional question.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --resume)
      if [[ -z "${2:-}" ]]; then
        echo "Error: --resume requires a session identifier or path" >&2
        exit 1
      fi
      RESUME_SESSION="$2"
      shift 2
      ;;
    *)
      if [[ -n "$QUESTION" ]]; then
        echo "Error: multiple positional arguments detected. Please quote the prompt." >&2
        exit 1
      fi
      # Consume the rest of the arguments as the question.
      QUESTION="$*"
      break
      ;;
  esac
done

if [[ -z "$RESUME_SESSION" && -z "$QUESTION" ]]; then
  echo "Usage: $0 \"YOUR QUESTION\"" >&2
  echo "       $0 --resume <session_id_or_path>" >&2
  exit 1
fi

# --- Configuration ---
CHAINS="${CHAINS:-10}"
MAJ_MIN="${MAJ_MIN:-0.5}"
MAX_ROUNDS="${MAX_ROUNDS:-3}"

# --- Session Initialization ---
if [[ -n "$RESUME_SESSION" ]]; then
  # If resuming, find the absolute path to the session directory
  if [[ -d "$RESUME_SESSION" ]]; then
    SESSION_DIR="$(cd "$RESUME_SESSION" && pwd)"
  else
    SESSION_DIR="$DIR/runs/$RESUME_SESSION"
  fi

  if [[ ! -d "$SESSION_DIR" || ! -f "$SESSION_DIR/manifest.json" ]]; then
    echo "Error: Cannot resume. Session directory or manifest.json not found at '$SESSION_DIR'" >&2
    exit 1
  fi
  SESSION_ID="$(basename "$SESSION_DIR")"
  echo "[*] Resuming session: $SESSION_ID"

  # Load parameters from the session's manifest to ensure consistency
  QUESTION=$(jq -r '.question' "$SESSION_DIR/manifest.json")
  CHAINS=$(jq -r '.parameters.CHAINS' "$SESSION_DIR/manifest.json")
  MAJ_MIN=$(jq -r '.parameters.MAJ_MIN' "$SESSION_DIR/manifest.json")
  MAX_ROUNDS=$(jq -r '.parameters.MAX_ROUNDS' "$SESSION_DIR/manifest.json")

  # Determine which round to start from
  last_round=$(find "$SESSION_DIR" -name "round_*" -type d | sed 's/.*round_//' | sort -n | tail -n 1)
  round=$(( ${last_round:-0} + 1 ))
  # Restore the chain count from the last successful round if possible
  if [[ ${last_round:-0} -gt 0 ]]; then
      last_chains=$(jq -r '.TOTAL_CHAINS' "$SESSION_DIR/round_$last_round/summary.env" 2>/dev/null || echo "$CHAINS")
      # Escalate for the next round
      curr_chains=$(( last_chains * 2 ))
  else
      curr_chains="$CHAINS"
  fi
else
  # Start a new session
  SESSION_ID="mjthinking_$(date +%Y%m%d_%H%M%S)_$$"
  SESSION_DIR="$DIR/runs/$SESSION_ID"
  mkdir -p "$SESSION_DIR"
  echo "[*] Session starting. All artifacts will be saved to:"
  echo "    $SESSION_DIR"

  # Save a manifest for reproducibility
  cat > "$SESSION_DIR/manifest.json" <<EOF
{
  "session_id": "$SESSION_ID",
  "question": "$QUESTION",
  "start_timestamp": "$(date +%s)",
  "parameters": {
    "CHAINS": "$CHAINS", "MAJ_MIN": "$MAJ_MIN", "MAX_ROUNDS": "$MAX_ROUNDS",
    "MODEL": "${MODEL:-"default"}", "PREDICT": "${PREDICT:-"default"}", "TEMP": "${TEMP:-"default"}"
  }
}
EOF
  round=1
  curr_chains="$CHAINS"
fi


# --- Main Loop ---
while [[ "$round" -le "$MAX_ROUNDS" ]]; do
  # Each round gets its own subdirectory
  ROUND_DIR="$SESSION_DIR/round_$round"
  mkdir -p "$ROUND_DIR"
  export MJTHINKING_ROUND_DIR="$ROUND_DIR"

  echo
  echo "[*] Round $round — running $curr_chains chains…"
  if ! "$DIR/mjthinking_core.sh" "$QUESTION" "$curr_chains"; then
      if [[ $? -eq 2 ]]; then
          echo "[!] No 'Final Answer' lines found in any chain for round $round."
      else
          echo "[!] Core runner failed for round $round. Aborting." >&2
          exit 1
      fi
  fi

  SUMMARY_FILE="$ROUND_DIR/summary.env"
  if [[ ! -f "$SUMMARY_FILE" ]]; then
      echo "[!] No summary found in $ROUND_DIR. Creating best-effort result."
      # Create a dummy summary to avoid script failure
      {
        echo "FINAL_ANSWER=[No consensus answer found]"
        echo "FINAL_COUNT=0"
        echo "TOTAL_CHAINS=$curr_chains"
      } > "$SUMMARY_FILE"
  fi
  source "$SUMMARY_FILE"
  FA="${FINAL_ANSWER:-}"; FC="${FINAL_COUNT:-0}"; TOT="${TOTAL_CHAINS:-$curr_chains}"

  echo "[*] Majority: $FC / $TOT"
  maj_req=$(python3 -c "import math; print(math.ceil(float($MAJ_MIN) * $TOT if $TOT > 0 else 0))" 2>/dev/null || echo "$(((TOT / 2) + 1))")

  # --- Verification ---
  RVER="UNKNOWN"
  if [[ -n "$FA" && "$FA" != "[No consensus answer found]" ]]; then
      # Safely execute referee script
      RVER_OUTPUT=$("$DIR/referee.sh" "$QUESTION" "$FA" 2>/dev/null || echo "VERDICT=FAIL")
      RVER=$(echo "$RVER_OUTPUT" | grep '^VERDICT=' | cut -d= -f2)
      [ -z "$RVER" ] && RVER="FAIL"
  fi
  echo "[*] Referee verdict: $RVER"

  NVER="UNKNOWN"
  if [[ -n "$FA" && "$FA" != "[No consensus answer found]" ]]; then
      # Safely execute numeric evaluation
      NVER=$(python3 "$DIR/arith_eval.py" "$QUESTION" "$FA" 2>/dev/null || echo "FAIL")
      [ -z "$NVER" ] && NVER="FAIL"
  fi
  echo "[*] Numeric check: $NVER"

  # --- Decision Logic ---
  pass_majority=$([ "$FC" -ge "$maj_req" ] && [ "$FC" -gt 0 ] && echo YES || echo NO)
  pass_ref=$([ "$RVER" = "PASS" ] && echo YES || echo NO)

  if [ "$pass_majority" = "YES" ] && [ "$pass_ref" = "YES" ]; then
    echo
    echo "================== MJTHINKING RESULT =================="
    echo "Final Answer: $FA"
    echo "(Majority $FC/$TOT • Referee PASS • Numeric $NVER)"
    echo "All traces under: $SESSION_DIR"
    echo "====================================================="
    ln -snf "$SESSION_DIR" "$DIR/runs/latest"
    exit 0
  fi

  if [ "$round" -ge "$MAX_ROUNDS" ]; then
    echo
    echo "================== MJTHINKING (BEST EFFORT) ========="
    echo "Final Answer: $FA"
    echo "(Majority $FC/$TOT • Referee $RVER • Numeric $NVER)"
    echo "Reached MAX_ROUNDS=$MAX_ROUNDS. Inspect session for details:"
    echo "    $SESSION_DIR"
    echo "====================================================="
    ln -snf "$SESSION_DIR" "$DIR/runs/latest"
    exit 0
  fi

  # Escalate: double chains for the next round
  round=$((round+1))
  curr_chains=$((curr_chains*2))
done