#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

QUESTION="${1:-}"
CHAINS_IN="${2:-}"
MODEL_ARG="${3:-}"
[ -z "$QUESTION" ] && { echo "Usage: $0 \"YOUR QUESTION\" [CHAINS] [MODEL]"; exit 1; }

CHAINS="${CHAINS_IN:-${CHAINS:-10}}"
MODEL_DEFAULT="${MODEL:-google/gemma-3-12b}"
if [[ -n "$MODEL_ARG" ]]; then
  MODEL="$MODEL_ARG"
else
  MODEL="$MODEL_DEFAULT"
fi
CTX="${CTX:-4096}"
TEMP="${TEMP:-0.8}"
TOP_P="${TOP_P:-0.95}"
PREDICT="${PREDICT:-900}"
API="${API:-http://127.0.0.1:11434}"
API_TYPE="${API_TYPE:-}"
if [[ -z "$API_TYPE" ]]; then
  if [[ "$API" == *"/v1"* ]] || [[ "$API" == *":1234"* ]]; then
    API_TYPE="openai"
  else
    API_TYPE="ollama"
  fi
fi
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

echo "[*] Launching $CHAINS chains on $MODEL (ctx=$CTX, temp=$TEMP, top_p=$TOP_P, max_new=$PREDICT) via ${API_TYPE} @ ${API}..."
pids=()
for i in $(seq 1 "$CHAINS"); do
  SEED=$(( (RANDOM << 16) ^ RANDOM ^ i ))
  OUT="$RUNS_DIR/$i.json"
  (
    if [[ "$API_TYPE" == "openai" ]]; then
      BASE="${API%/}"
      if [[ "$BASE" != *"/v1" ]]; then
        BASE="$BASE/v1"
      fi
      BODY="$(jq -n \
        --arg model "$MODEL" \
        --arg prompt "$PROMPT" \
        --argjson temperature "$TEMP" \
        --argjson top_p "$TOP_P" \
        --argjson max_tokens "$PREDICT" \
        '{model:$model,prompt:$prompt,temperature:$temperature,top_p:$top_p,max_tokens:$max_tokens,n:1,stream:false}'
      )"
      if [[ -n "${API_KEY:-${OPENAI_API_KEY:-}}" ]]; then
        KEY="${API_KEY:-${OPENAI_API_KEY:-}}"
        RESP="$(curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d "$BODY" "$BASE/completions")"
      else
        RESP="$(curl -s -H "Content-Type: application/json" -d "$BODY" "$BASE/completions")"
      fi
      if [[ -z "$RESP" ]]; then
        echo '{"error":"empty response","response":""}' > "$OUT"
      else
        TEXT="$(printf '%s\n' "$RESP" | jq -r '(.choices[0].text // .choices[0].message.content // .output_text // "")')"
        printf '%s\n' "$RESP" | jq --arg response "$TEXT" '{response:$response,raw:.}' > "$OUT"
      fi
    else
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
    fi
  ) & pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done

# Extract responses; tally one "Final Answer:" per trace
for f in "$RUNS_DIR"/*.json; do jq -r '.response' "$f" > "${f%.json}.txt"; done
answers=()
for t in "$RUNS_DIR"/*.txt; do
  clean="$(python3 - "$t" <<'PY'
import re, sys, pathlib

path = pathlib.Path(sys.argv[1])
try:
    lines = path.read_text().splitlines()
except FileNotFoundError:
    sys.exit(0)

answer = ""
for idx, line in enumerate(lines):
    m = re.search(r'Final Answer:\s*(.*)', line, flags=re.I)
    if not m:
        continue
    candidate = m.group(1).strip()
    if not candidate and idx + 1 < len(lines):
        candidate = lines[idx + 1].strip()
    answer = candidate.strip()

if answer:
    if re.fullmatch(r'\*\*[^*]+\*\*', answer):
        answer = answer[2:-2]
    boxed = re.fullmatch(r'\\boxed\{(.*)\}', answer)
    if boxed:
        answer = boxed.group(1)
    dollar = re.fullmatch(r'\$([^$]*)\$', answer)
    if dollar:
        answer = dollar.group(1)
    answer = answer.strip()
print(answer)
PY
)"
  if [[ -n "$clean" ]]; then
    answers+=("$clean")
  fi
done
if ((${#answers[@]} > 0)); then
  printf '%s\n' "${answers[@]}" | sort | uniq -c | sort -nr > "$RUNS_DIR/votes.txt"
else
  : > "$RUNS_DIR/votes.txt"
fi

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
