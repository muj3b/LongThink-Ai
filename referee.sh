#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

QUESTION="${1:-}"
CANDIDATE="${2:-}"
[ -z "$QUESTION" ] && { echo "Usage: $0 \"QUESTION\" \"CANDIDATE_FINAL_ANSWER\""; exit 1; }

MODEL="${MODEL:-deepseek-r1:7b}"
CTX="${CTX:-4096}"
TEMP="${TEMP:-0.2}"      # low temp for verifier stability
TOP_P="${TOP_P:-0.9}"
PREDICT="${PREDICT:-600}"
API="${API:-http://127.0.0.1:11434}"

REFP="$(cat "$DIR/referee_prompt.txt")

Candidate Final Answer: ${CANDIDATE}

Question:
${QUESTION}
"

BODY="$(jq -n \
  --arg model "$MODEL" \
  --arg prompt "$REFP" \
  --argjson num_ctx "$CTX" \
  --argjson temperature "$TEMP" \
  --argjson top_p "$TOP_P" \
  --argjson num_predict "$PREDICT" \
  '{model:$model,prompt:$prompt,stream:false,
    options:{temperature:$temperature,num_ctx:$num_ctx,top_p:$top_p,num_predict:$num_predict}}'
)"
RESP="$(curl -s "$API/api/generate" -H "Content-Type: application/json" -d "$BODY")"
TEXT="$(jq -r '.response' <<< "$RESP")"

echo "$TEXT" > "$DIR/runs/referee.txt"

# Extract VERDICT line
VERDICT="$(printf "%s\n" "$TEXT" | grep -E '^\s*VERDICT:\s*(PASS|FAIL)\s*$' | tail -n 1 | awk -F: '{print $2}' | tr -d '[:space:]')"
[ -z "$VERDICT" ] && VERDICT="UNKNOWN"

echo "VERDICT=$VERDICT"
