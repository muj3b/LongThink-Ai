#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

QUESTION="${1:-}"
CHAINS_IN="${2:-}"
[ -z "$QUESTION" ] && { echo "Usage: $0 \"YOUR QUESTION\" [CHAINS]"; exit 1; }

CHAINS="${CHAINS_IN:-${CHAINS:-10}}"
MODEL="${MODEL:-deepseek-r1:7b}"
CTX="${CTX:-4096}"
TEMP="${TEMP:-0.8}"
TOP_P="${TOP_P:-0.95}"
PREDICT="${PREDICT:-900}"
API="${API:-http://127.0.0.1:11434}"

# Use round-specific directory if provided by orchestrator, default to runs/
RUNS_DIR="${MJTHINKING_ROUND_DIR:-$DIR/runs}"
mkdir -p "$RUNS_DIR"
# Clean slate for the round
rm -f "$RUNS_DIR"/*.json "$RUNS_DIR"/*.txt "$RUNS_DIR/votes.txt"

PROMPT="$(cat "$DIR/prompt_template.txt")

Question:
${QUESTION}
"

echo "[*] Launching $CHAINS chains on $MODEL (ctx=$CTX, temp=$TEMP, top_p=$TOP_P, max_new=$PREDICT)…"
pids=()
for i in $(seq 1 "$CHAINS"); do
  SEED=$(( (RANDOM << 16) ^ RANDOM ^ i ))
  OUT="$RUNS_DIR/$i.json"
  (
    BODY="$(jq -n \
      --arg model "$MODEL" \
      --arg prompt "$PROMPT" \
      --argjson num_ctx "$CTX" \
      --argjson temperature "$TEMP" \
      --argjson top_p "$TOP_P" \
      --argjson num_predict "$PREDICT" \
      --argjson seed "$SEED" \
      '{model:$model,prompt:$prompt,stream:false,
        options:{temperature:$temperature,num_ctx:$num_ctx,top_p:$top_p,num_predict:$num_predict,seed:$seed}}'
    )"
    curl -s "$API/api/generate" -H "Content-Type: application/json" -d "$BODY" > "$OUT"
  ) & pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done

# Extract responses; tally "Final Answer:" lines
for f in "$RUNS_DIR"/*.json; do jq -r '.response' "$f" > "${f%.json}.txt"; done
# Canonicalize the 'Final Answer:' lines for accurate voting.
# This single sed command removes the prefix, trims whitespace, and strips common formatting.
grep -h "Final Answer:" "$RUNS_DIR"/*.txt \
  | sed -E \
      -e 's/.*Final Answer:[[:space:]]*//' \
      -e 's/^\s+|\s+$//g' \
      -e 's/^\\*\\*([^*]+)\\*\\*$/\1/' \
      -e 's/^\\boxed\{(.*)\}$/\1/' \
      -e 's/^\$([^\$]*)\$$/\1/' \
      -e 's/^\s+|\s+$//g' \
  | sort | uniq -c | sort -nr > "$RUNS_DIR/votes.txt" || true

echo "================== VOTE TALLY (top 5) =================="
(head -n 5 "$RUNS_DIR/votes.txt" || echo "No 'Final Answer:' lines found") | cat
echo "========================================================"

TOP_ANSWER="$( (head -n 1 "$RUNS_DIR/votes.txt" 2>/dev/null || echo "") | sed 's/^ *[0-9][0-9]* *//' )"
TOP_COUNT="$( (head -n 1 "$RUNS_DIR/votes.txt" 2>/dev/null | awk '{print $1}') || echo 0 )"
TOTAL="$CHAINS"

# Write summary for orchestrator to source
echo "FINAL_ANSWER=$TOP_ANSWER" > "$RUNS_DIR/summary.env"
echo "FINAL_COUNT=$TOP_COUNT"   >> "$RUNS_DIR/summary.env"
echo "TOTAL_CHAINS=$TOTAL"      >> "$RUNS_DIR/summary.env"

# Show one winning trace
if [ -n "$TOP_ANSWER" ]; then
  echo
  echo "---- WINNING FINAL ANSWER ----"
  echo "$TOP_ANSWER"
  echo
  echo "---- ONE TRACE OF REASONING FOR WINNER ----"
  # Use grep's -l flag to find a matching file, then cat it.
  WINNING_FILE=$(grep -lF "Final Answer: $TOP_ANSWER" "$RUNS_DIR"/*.txt | head -n 1)
  if [[ -n "$WINNING_FILE" ]]; then
      cat "$WINNING_FILE"
  fi
else
  echo "[!] No final answers detected. Inspect individual traces in $RUNS_DIR/*.txt"
  # Exit with a special code the orchestrator can check
  exit 2
fi