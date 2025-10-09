#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

[ -z "${1:-}" ] && { echo "Usage: $0 \"QUESTION\" \"CANDIDATE_FINAL_ANSWER\" [MODEL]"; exit 1; }
QUESTION="$1"
CANDIDATE="${2:-}"
MODEL_ARG="${3:-}"

MODEL_DEFAULT="${MODEL:-google/gemma-3-12b}"
if [[ -n "$MODEL_ARG" ]]; then
  MODEL="$MODEL_ARG"
else
  MODEL="$MODEL_DEFAULT"
fi
CTX="${CTX:-4096}"
TEMP="${TEMP:-0.2}"      # low temp for verifier stability
TOP_P="${TOP_P:-0.9}"
PREDICT="${PREDICT:-600}"
API="${API:-http://127.0.0.1:11434}"
API_TYPE="${API_TYPE:-}"
if [[ -z "$API_TYPE" ]]; then
  if [[ "$API" == *"/v1"* ]] || [[ "$API" == *":1234"* ]]; then
    API_TYPE="openai"
  else
    API_TYPE="ollama"
  fi
fi

REFP="$(cat "$DIR/referee_prompt.txt")

Candidate Final Answer: ${CANDIDATE}

Question:
${QUESTION}
"

if [[ "$API_TYPE" == "openai" ]]; then
  BASE="${API%/}"
  if [[ "$BASE" != *"/v1" ]]; then
    BASE="$BASE/v1"
  fi
  BODY="$(jq -n \
    --arg model "$MODEL" \
    --arg prompt "$REFP" \
    --argjson temperature "$TEMP" \
    --argjson top_p "$TOP_P" \
    --argjson max_tokens "$PREDICT" \
    '{model:$model,prompt:$prompt,temperature:$temperature,top_p:$top_p,max_tokens:$max_tokens,n:1,stream:false}'
  )"
  AUTH_HEADER=()
  if [[ -n "${API_KEY:-${OPENAI_API_KEY:-}}" ]]; then
    KEY="${API_KEY:-${OPENAI_API_KEY:-}}"
    AUTH_HEADER=(-H "Authorization: Bearer $KEY")
  fi
  RESP="$(curl -s "${AUTH_HEADER[@]}" -H "Content-Type: application/json" -d "$BODY" "$BASE/completions")"
  TEXT="$(echo "$RESP" | jq -r '(.choices[0].text // .choices[0].message.content // .output_text // "")')"
else
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
fi

echo "$TEXT" > "$DIR/runs/referee.txt"

# Extract VERDICT line
VERDICT="$(printf "%s\n" "$TEXT" | grep -E '^\s*VERDICT:\s*(PASS|FAIL)\s*$' | tail -n 1 | awk -F: '{print $2}' | tr -d '[:space:]')"
[ -z "$VERDICT" ] && VERDICT="UNKNOWN"

echo "VERDICT=$VERDICT"
