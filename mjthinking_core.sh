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
RUNS_DIR="${MJTHINKING_ROUND_DIR:-$DIR/runs}"
PROMPTS_DIR="${PROMPTS_DIR:-$DIR/prompts}"
PROMPT_STYLE="${PROMPT_STYLE:-default}"
PROMPT_FILE_OVERRIDE="${PROMPT_FILE:-}"

mkdir -p "$RUNS_DIR"
rm -f "$RUNS_DIR"/*.json "$RUNS_DIR"/*.txt "$RUNS_DIR/votes.txt"

template_path=""
if [[ -n "$PROMPT_FILE_OVERRIDE" && -f "$PROMPT_FILE_OVERRIDE" ]]; then
  template_path="$PROMPT_FILE_OVERRIDE"
else
  style_path="$PROMPTS_DIR/${PROMPT_STYLE}.txt"
  if [[ -f "$style_path" ]]; then
    template_path="$style_path"
  elif [[ -f "$DIR/prompt_template.txt" ]]; then
    template_path="$DIR/prompt_template.txt"
  fi
fi

if [[ -z "$template_path" ]]; then
  echo "[!] Prompt template not found for style '$PROMPT_STYLE'" >&2
  echo "    Checked: ${PROMPT_FILE_OVERRIDE:-'(PROMPT_FILE unset)'} and $PROMPTS_DIR/${PROMPT_STYLE}.txt" >&2
  echo "    Ensure prompt templates exist under prompts/" >&2
  exit 1
fi

PROMPT="$(cat "$template_path")

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
grep -h "Final Answer:" "$RUNS_DIR"/*.txt | sed -E 's/.*Final Answer:[[:space:]]*//' | sed -E 's/[[:space:]]+$//' \
  | sed -E 's/^\\*\\*([^*]+)\\*\\*$/\\1/' \
  | sed -E 's/^\\\\boxed\\{(.*)\\}$/\\1/' \
  | sed -E 's/^\\$([^$]*)\\$$/\\1/' \
  | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' \
  | sort | uniq -c | sort -nr > "$RUNS_DIR/votes.txt" || true

echo "================== MJTHINKING VOTE TALLY (top 5) =================="
(head -n 5 "$RUNS_DIR/votes.txt" || echo "No 'Final Answer:' lines found") | cat
echo "=================================================================="

TOP_ANSWER="$( (head -n 1 "$RUNS_DIR/votes.txt" 2>/dev/null || echo "") | sed 's/^ *[0-9][0-9]* *//' )"
TOP_COUNT="$( (head -n 1 "$RUNS_DIR/votes.txt" 2>/dev/null | awk '{print $1}') || echo 0 )"
TOTAL="$CHAINS"

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
  for t in "$RUNS_DIR"/*.txt; do
    if grep -Fq "Final Answer: $TOP_ANSWER" "$t"; then
      cat "$t"
      break
    fi
  done
else
  echo "[!] No final answers detected. Inspect individual traces in $RUNS_DIR/*.txt"
  exit 2
fi
