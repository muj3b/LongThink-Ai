#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

QUESTION=""
RESUME_SESSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --resume=*)
      RESUME_SESSION="${1#*=}"
      shift
      ;;
    --resume)
      if [[ $# -lt 2 ]]; then
        echo "Error: --resume requires a session identifier or path" >&2
        exit 1
      fi
      RESUME_SESSION="$2"
      shift 2
      ;;
    *)
      if [[ -n "$QUESTION" ]]; then
        echo "Error: multiple positional arguments detected. Quote the prompt." >&2
        exit 1
      fi
      QUESTION="$*"
      break
      ;;
  esac
done

if [[ -z "$RESUME_SESSION" && -z "$QUESTION" ]]; then
  echo "Usage: $0 \"YOUR QUESTION\" [--resume <session_id|path>]" >&2
  exit 1
fi

CHAINS="${CHAINS:-10}"
MAJ_MIN="${MAJ_MIN:-0.5}"   # e.g., 0.5 requires simple majority
MAX_ROUNDS="${MAX_ROUNDS:-3}"
PROMPT_STYLE="${PROMPT_STYLE:-default}"
PROMPTS_DIR="${PROMPTS_DIR:-$DIR/prompts}"
mkdir -p "$PROMPTS_DIR"
PLUGINS_DIR="${PLUGINS_DIR:-$DIR/plugins}"
mkdir -p "$PLUGINS_DIR"
PROGRESS_UPDATE_INTERVAL="${PROGRESS_UPDATE_INTERVAL:-0}"
EMA_ALPHA_VALUE="${EMA_ALPHA:-60}"


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

time_progress_bar() {
  local elapsed=${1:-0}
  local budget=${2:-0}
  local width=${3:-28}
  if (( budget <= 0 )); then
    printf '[progress unavailable]'
    return 0
  fi
  local percent=$(( elapsed * 100 / budget ))
  if (( percent < 0 )); then percent=0; fi
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
prev_elapsed_total=0
prev_conf_ratio="0"
last_progress_print=0
RESUME_MODE=0

if [[ -n "$RESUME_SESSION" ]]; then
  RESUME_MODE=1
  if [[ -d "$RESUME_SESSION" ]]; then
    SESSION_DIR="$(cd "$RESUME_SESSION" && pwd)"
  else
    SESSION_DIR="$DIR/runs/$RESUME_SESSION"
  fi
  if [[ ! -d "$SESSION_DIR" ]]; then
    echo "Error: resume session directory not found: $RESUME_SESSION" >&2
    exit 1
  fi
  SESSION_ID="$(basename "$SESSION_DIR")"
else
  if [[ -z "${SESSION_ID:-}" ]]; then
    SESSION_ID="mjthinking_$(date +%Y%m%d_%H%M%S)_$$"
  fi
  SESSION_DIR="$DIR/runs/$SESSION_ID"
fi

mkdir -p "$SESSION_DIR"
META_FILE="$SESSION_DIR/session.jsonl"
touch "$META_FILE"
SUMMARY_MD="$SESSION_DIR/summary.md"
MANIFEST_FILE="$SESSION_DIR/manifest.json"
STATE_FILE="$SESSION_DIR/state.json"
export SESSION_ID SESSION_DIR META_FILE MANIFEST_FILE STATE_FILE PROMPTS_DIR PLUGINS_DIR
export MJTHINKING_SESSION_DIR="$SESSION_DIR"
export PROMPT_STYLE
WEBHOOK_URL="${MJTHINKING_WEBHOOK_URL:-}"
WEBHOOK_TIMEOUT="${MJTHINKING_WEBHOOK_TIMEOUT:-2}"
ENABLE_NOTIFY="${MJTHINKING_NOTIFY:-}"
TARGET_CONF="${TARGET_CONF:-}"
AUTO_EXTEND_ROUNDS="${AUTO_EXTEND_ROUNDS:-0}"
VALIDATOR_HOOKS="${VALIDATOR_HOOKS:-}"
VALIDATORS_DIR="${VALIDATORS_DIR:-$DIR/validators}"
ROUND_HISTORY_FILE="$DIR/runs/history_rounds.jsonl"
mkdir -p "$DIR/runs"
touch "$ROUND_HISTORY_FILE"
AUTO_EXTEND_REMAINING="$AUTO_EXTEND_ROUNDS"
HISTORY_MEAN_DURATION=$(python3 - <<'PY'
import json, statistics, pathlib

path = pathlib.Path(__import__('os').environ.get('ROUND_HISTORY_FILE', ''))
durations = []
if path.is_file():
    with path.open('r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get('event') != 'round_complete':
                continue
            duration = event.get('round_duration')
            if isinstance(duration, int) and duration > 0:
                durations.append(duration)

if durations:
    print(int(round(statistics.mean(durations))))
else:
    print(0)
PY
)
[ -n "$HISTORY_MEAN_DURATION" ] || HISTORY_MEAN_DURATION=0

echo "[*] Session ID: $SESSION_ID"
if [[ $RESUME_MODE -eq 1 ]]; then
  if [[ ! -f "$MANIFEST_FILE" ]]; then
    echo "Error: manifest.json missing in session directory" >&2
    exit 1
  fi
  eval "$(MANIFEST_FILE="$MANIFEST_FILE" python3 - <<'PY'
import base64, json, os

path = os.environ["MANIFEST_FILE"]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

question = data.get("question") or ""
start_ts = data.get("start_timestamp") or 0
rounds = data.get("rounds") or []
last_round = rounds[-1]["round"] if rounds else 0
last_elapsed = rounds[-1].get("elapsed_seconds", 0) if rounds else 0
params = data.get("parameters", {})
manifest_chains = params.get("CHAINS")
manifest_max_rounds = params.get("MAX_ROUNDS")
manifest_maj_min = params.get("MAJ_MIN")
manifest_time_budget = params.get("TIME_BUDGET")
manifest_mode = params.get("MODE")
manifest_model = params.get("MODEL")
manifest_model_fallback = params.get("MODEL_FALLBACK")
manifest_prompt_style = params.get("PROMPT_STYLE")
manifest_prompts_dir = params.get("PROMPTS_DIR")
manifest_plugins_dir = params.get("PLUGINS_DIR")

print(f'export RESUME_START_TS="{start_ts}"')
print(f'export RESUME_LAST_ROUND="{last_round}"')
print(f'export RESUME_LAST_ELAPSED="{last_elapsed}"')
print(f'export RESUME_MANIFEST_CHAINS="{manifest_chains or ""}"')
print('export RESUME_QUESTION_B64="' + base64.b64encode(question.encode()).decode() + '"')
print(f'export RESUME_MANIFEST_MAX_ROUNDS="{manifest_max_rounds or ""}"')
print(f'export RESUME_MANIFEST_MAJ_MIN="{manifest_maj_min or ""}"')
print(f'export RESUME_MANIFEST_TIME_BUDGET="{manifest_time_budget or ""}"')
print(f'export RESUME_MANIFEST_MODE="{manifest_mode or ""}"')
print(f'export RESUME_MANIFEST_MODEL="{manifest_model or ""}"')
print(f'export RESUME_MANIFEST_MODEL_FALLBACK="{manifest_model_fallback or ""}"')
print(f'export RESUME_MANIFEST_PROMPT_STYLE="{manifest_prompt_style or ""}"')
print(f'export RESUME_MANIFEST_PROMPTS_DIR="{manifest_prompts_dir or ""}"')
print(f'export RESUME_MANIFEST_PLUGINS_DIR="{manifest_plugins_dir or ""}"')
PY
)"
  if [[ -f "$STATE_FILE" ]]; then
    eval "$(STATE_FILE="$STATE_FILE" python3 - <<'PY'
import json, os

path = os.environ["STATE_FILE"]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception:
    data = {}

print(f'export STATE_LAST_ROUND="{data.get("last_round", "")}"')
print(f'export STATE_NEXT_ROUND="{data.get("next_round", "")}"')
print(f'export STATE_NEXT_CHAINS="{data.get("next_chains", "")}"')
print(f'export STATE_ELAPSED="{data.get("elapsed_seconds", "")}"')
print(f'export STATE_STATUS="{data.get("status", "in_progress")}"')
print(f'export STATE_AUTO_EXTEND="{data.get("auto_extend_remaining", "")}"')
PY
)"
  fi
  if [[ -n "${RESUME_QUESTION_B64:-}" && -z "$QUESTION" ]]; then
    QUESTION=$(RESUME_QUESTION_B64="$RESUME_QUESTION_B64" python3 - <<'PY'
import base64, os
print(base64.b64decode(os.environ["RESUME_QUESTION_B64"]).decode(), end="")
PY
)
  fi
  START_TS=${RESUME_START_TS:-0}
  if [[ -z "$QUESTION" ]]; then
    echo "Error: unable to determine question for resumed session" >&2
    exit 1
  fi
  last_round_completed=${RESUME_LAST_ROUND:-0}
  prev_elapsed_total=${STATE_ELAPSED:-${RESUME_LAST_ELAPSED:-0}}
  if [[ -n "${STATE_NEXT_ROUND:-}" ]]; then
    round=$STATE_NEXT_ROUND
  else
    round=$(( last_round_completed + 1 ))
  fi
  if [[ -n "${RESUME_MANIFEST_CHAINS:-}" && "$CHAINS" = "10" ]]; then
    CHAINS="$RESUME_MANIFEST_CHAINS"
  fi
  if [[ -n "${RESUME_MANIFEST_MAX_ROUNDS:-}" ]]; then
    MAX_ROUNDS="$RESUME_MANIFEST_MAX_ROUNDS"
  fi
  if [[ -n "${RESUME_MANIFEST_MAJ_MIN:-}" ]]; then
    MAJ_MIN="$RESUME_MANIFEST_MAJ_MIN"
  fi
  if [[ -n "${RESUME_MANIFEST_TIME_BUDGET:-}" ]]; then
    TIME_BUDGET="$RESUME_MANIFEST_TIME_BUDGET"
  fi
  if [[ -n "${RESUME_MANIFEST_MODE:-}" ]]; then
    MODE="$RESUME_MANIFEST_MODE"
  fi
  if [[ -n "${RESUME_MANIFEST_MODEL:-}" ]]; then
    MODEL="$RESUME_MANIFEST_MODEL"
  fi
  if [[ -n "${RESUME_MANIFEST_MODEL_FALLBACK:-}" ]]; then
    MODEL_FALLBACK="$RESUME_MANIFEST_MODEL_FALLBACK"
  fi
  if [[ -n "${RESUME_MANIFEST_PROMPT_STYLE:-}" ]]; then
    PROMPT_STYLE="$RESUME_MANIFEST_PROMPT_STYLE"
  fi
  if [[ -n "${RESUME_MANIFEST_PROMPTS_DIR:-}" ]]; then
    PROMPTS_DIR="$RESUME_MANIFEST_PROMPTS_DIR"
  fi
  if [[ -n "${RESUME_MANIFEST_PLUGINS_DIR:-}" ]]; then
    PLUGINS_DIR="$RESUME_MANIFEST_PLUGINS_DIR"
  fi
  mkdir -p "$PROMPTS_DIR"
  mkdir -p "$PLUGINS_DIR"
  if [[ -n "${STATE_AUTO_EXTEND:-}" ]]; then
    AUTO_EXTEND_REMAINING="$STATE_AUTO_EXTEND"
  fi
  if [[ -n "${STATE_NEXT_CHAINS:-}" ]]; then
    curr_chains="$STATE_NEXT_CHAINS"
  else
    curr_chains="$CHAINS"
  fi
  unset RESUME_START_TS RESUME_LAST_ROUND RESUME_LAST_ELAPSED RESUME_MANIFEST_CHAINS RESUME_QUESTION_B64 RESUME_MANIFEST_MAX_ROUNDS RESUME_MANIFEST_MAJ_MIN RESUME_MANIFEST_TIME_BUDGET RESUME_MANIFEST_MODE RESUME_MANIFEST_MODEL RESUME_MANIFEST_MODEL_FALLBACK RESUME_MANIFEST_PROMPT_STYLE RESUME_MANIFEST_PROMPTS_DIR RESUME_MANIFEST_PLUGINS_DIR STATE_LAST_ROUND STATE_NEXT_ROUND STATE_NEXT_CHAINS STATE_ELAPSED STATE_STATUS STATE_AUTO_EXTEND
else
  START_TS=$(date +%s)
  round=1
  prev_elapsed_total=0
  curr_chains="$CHAINS"
  QUESTION_VALUE="$QUESTION" \
  CHAINS_VALUE="$CHAINS" \
  MAX_ROUNDS_VALUE="$MAX_ROUNDS" \
  MAJ_MIN_VALUE="$MAJ_MIN" \
  START_TS_VALUE="$START_TS" \
  MANIFEST_FILE="$MANIFEST_FILE" \
  MJ_RETRIES_VALUE="${MJTHINKING_RETRIES:-}" \
  TIME_BUDGET_VALUE="${TIME_BUDGET:-}" \
  MODE_VALUE="${MODE:-}" \
  MODEL_VALUE="${MODEL:-}" \
  MODEL_FALLBACK_VALUE="${MODEL_FALLBACK:-}" \
  PROMPT_STYLE_VALUE="${PROMPT_STYLE:-}" \
  PROMPTS_DIR_VALUE="${PROMPTS_DIR:-}" \
  PLUGINS_DIR_VALUE="${PLUGINS_DIR:-}" \
  WEBHOOK_URL_VALUE="$WEBHOOK_URL" \
  TARGET_CONF_VALUE="$TARGET_CONF" \
  AUTO_EXTEND_VALUE="$AUTO_EXTEND_ROUNDS" \
  VALIDATOR_HOOKS_VALUE="$VALIDATOR_HOOKS" \
  python3 - <<'PY'
import json, os

manifest = {
    "session_id": os.environ.get("SESSION_ID"),
    "question": os.environ.get("QUESTION_VALUE"),
    "start_timestamp": int(os.environ.get("START_TS_VALUE", "0")),
    "parameters": {
        "CHAINS": os.environ.get("CHAINS_VALUE"),
        "MAX_ROUNDS": os.environ.get("MAX_ROUNDS_VALUE"),
        "MAJ_MIN": os.environ.get("MAJ_MIN_VALUE"),
        "TIME_BUDGET": os.environ.get("TIME_BUDGET_VALUE"),
        "MODE": os.environ.get("MODE_VALUE"),
        "MODEL": os.environ.get("MODEL_VALUE"),
        "MODEL_FALLBACK": os.environ.get("MODEL_FALLBACK_VALUE"),
        "PROMPT_STYLE": os.environ.get("PROMPT_STYLE_VALUE"),
        "PROMPTS_DIR": os.environ.get("PROMPTS_DIR_VALUE"),
        "PLUGINS_DIR": os.environ.get("PLUGINS_DIR_VALUE"),
        "MJTHINKING_RETRIES": os.environ.get("MJ_RETRIES_VALUE"),
        "WEBHOOK_URL": os.environ.get("WEBHOOK_URL_VALUE"),
        "TARGET_CONF": os.environ.get("TARGET_CONF_VALUE"),
        "AUTO_EXTEND_ROUNDS": os.environ.get("AUTO_EXTEND_VALUE"),
        "VALIDATOR_HOOKS": os.environ.get("VALIDATOR_HOOKS_VALUE"),
    },
    "rounds": []
}

with open(os.environ.get("MANIFEST_FILE"), "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)
PY
  cat <<EOF > "$STATE_FILE"
{
  "session_id": "$SESSION_ID",
  "last_round": 0,
  "timestamp": $START_TS
}
EOF
fi

if [[ $RESUME_MODE -eq 1 ]]; then
  RESUME_JSON=$(python3 - <<'PY'
import json, os, time

payload = {
    "event": "session_resume",
    "session_id": os.environ.get("SESSION_ID"),
    "timestamp": int(time.time())
}
print(json.dumps(payload))
PY
)
  append_event "$RESUME_JSON"
  run_plugins "session_resume" "$SESSION_DIR" "$SESSION_ID"
else
  SESSION_JSON=$(QUESTION="$QUESTION" CHAINS="$CHAINS" START_TS="$START_TS" python3 - <<'PY'
import json, os

payload = {
    "event": "session_start",
    "session_id": os.environ.get("SESSION_ID"),
    "question": os.environ.get("QUESTION", ""),
    "chains": int(os.environ.get("CHAINS", "0")),
    "timestamp": int(os.environ.get("START_TS", "0")),
}
print(json.dumps(payload))
PY
)
  append_event "$SESSION_JSON"
  run_plugins "session_start" "$SESSION_DIR" "$SESSION_ID" "$QUESTION"
fi

send_webhook() {
  local payload="$1"
  [ -z "$WEBHOOK_URL" ] && return 0
  curl -sS -m "$WEBHOOK_TIMEOUT" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$WEBHOOK_URL" >/dev/null 2>&1 || true
}

run_plugins() {
  local hook="$1"
  shift || true
  local plugins=("$PLUGINS_DIR"/*.sh "$PLUGINS_DIR"/*.py)
  for plugin in "${plugins[@]}"; do
    [[ -e "$plugin" ]] || continue
    if [[ -x "$plugin" ]]; then
      HOOK="$hook" "$plugin" "$@" || true
    elif [[ "$plugin" == *.py ]]; then
      HOOK="$hook" python3 "$plugin" "$@" || true
    fi
  done
}

append_event() {
  local payload="$1"
  [ -z "$payload" ] && return 0
  echo "$payload" >> "$META_FILE"
  send_webhook "$payload"
}

notify_user() {
  [ -n "$ENABLE_NOTIFY" ] || return 0
  local status_msg="$1"
  local body_msg="$2"
  if command -v osascript >/dev/null 2>&1; then
    STATUS_NOTE="$status_msg" \
    BODY_NOTE="$body_msg" \
    osascript <<'OSA' >/dev/null 2>&1
set statusText to system attribute "STATUS_NOTE"
set bodyText to system attribute "BODY_NOTE"
display notification bodyText with title "MJThinking" subtitle statusText
OSA
  fi
}

CTL_FILE="$SESSION_DIR/control.ctl"
if [ ! -f "$CTL_FILE" ]; then
  echo "RUN" > "$CTL_FILE"
fi
export MJTHINKING_CTL_FILE="$CTL_FILE"
LAST_CONTROL_STATE="RUNNING"
prev_elapsed_total=0

log_control_event() {
  EVENT_TYPE="$1" \
  EVENT_NOTE="${2:-}" \
  CONTROL_JSON=$(python3 - <<'PY'
import json, os, time

payload = {
    "event": os.environ.get("EVENT_TYPE"),
    "session_id": os.environ.get("SESSION_ID"),
    "timestamp": int(time.time()),
}
note = os.environ.get("EVENT_NOTE")
if note:
    payload["note"] = note
print(json.dumps(payload))
PY
  )
  append_event "$CONTROL_JSON"
}

log_session_complete() {
  local status="$1"
  local reason="${2:-}"
  local rounds_value="${3:-$round}"
  local elapsed_value="${4:-$elapsed}"
  run_plugins "session_complete" "$SESSION_DIR" "$status" "$reason"
  STATUS="$status" \
  REASON="$reason" \
  ROUND_VALUE="$rounds_value" \
  ELAPSED_VALUE="$elapsed_value" \
  REF_VER="${RVER:-UNKNOWN}" \
  NUM_VER="${NVER:-UNKNOWN}" \
  FINAL_ANSWER_VALUE="${FA:-}" \
  COMPLETION_JSON=$(python3 - <<'PY'
import json, os, time

payload = {
    "event": "session_complete",
    "session_id": os.environ.get("SESSION_ID"),
    "status": os.environ.get("STATUS"),
    "final_answer": os.environ.get("FINAL_ANSWER_VALUE", ""),
    "referee_verdict": os.environ.get("REF_VER", "UNKNOWN"),
    "numeric_verdict": os.environ.get("NUM_VER", "UNKNOWN"),
    "rounds": int(os.environ.get("ROUND_VALUE", "0")),
    "elapsed_seconds": int(os.environ.get("ELAPSED_VALUE", "0")),
    "timestamp": int(time.time()),
}
reason = os.environ.get("REASON")
if reason:
    payload["reason"] = reason
print(json.dumps(payload))
PY
  )
  append_event "$COMPLETION_JSON"

  SUMMARY_JSON="$COMPLETION_JSON" \
  CURRENT_ROUND="$round" \
  FINAL_SUMMARY_MD="$SUMMARY_MD" \
  FINAL_SUMMARY_HTML="$SESSION_DIR/summary.html" \
  FINAL_SUMMARY_JSON="$SESSION_DIR/summary.json" \
  python3 - <<'PY'
import datetime
import html
import json
import os
from pathlib import Path
import textwrap

summary_md_path = Path(os.environ.get("FINAL_SUMMARY_MD"))
summary_html_path = Path(os.environ.get("FINAL_SUMMARY_HTML"))
summary_json_path = Path(os.environ.get("FINAL_SUMMARY_JSON"))
manifest_path = Path(os.environ.get("MANIFEST_FILE"))

summary_md_path.parent.mkdir(parents=True, exist_ok=True)

event = json.loads(os.environ.get("SUMMARY_JSON", "{}"))
elapsed = event.get("elapsed_seconds")

if manifest_path.is_file():
    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
else:
    manifest = {}

rounds = manifest.get("rounds", [])
question = manifest.get("question")
parameters = manifest.get("parameters", {})

def format_duration(seconds):
    if seconds is None:
        return "--"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return "".join(parts)

generated_iso = datetime.datetime.utcnow().isoformat() + "Z"

# Markdown summary
final_answer = event.get("final_answer") or "(none)"
with summary_md_path.open("w", encoding="utf-8") as fh:
    fh.write("# MJThinking Session Summary\n\n")
    fh.write(f"- **Session ID:** {event.get('session_id')}\n")
    fh.write(f"- **Status:** {event.get('status')}\n")
    fh.write(f"- **Rounds:** {event.get('rounds')}\n")
    fh.write(f"- **Elapsed:** {format_duration(elapsed)}\n")
    fh.write(f"- **Referee Verdict:** {event.get('referee_verdict')}\n")
    fh.write(f"- **Numeric Check:** {event.get('numeric_verdict')}\n")
    reason = event.get("reason")
    if reason:
        fh.write(f"- **Notes:** {reason}\n")
    if question:
        fh.write(f"- **Question:** {question.strip()}\n")

    fh.write("\n## Final Answer\n\n")
    fh.write(textwrap.dedent(final_answer).strip() + "\n")

    fh.write("\n## Parameters\n\n")
    for key, value in sorted(parameters.items()):
        fh.write(f"- `{key}` = {value}\n")

    fh.write("\n## Rounds\n\n")
    if rounds:
        for round_entry in rounds:
            fh.write(f"- Round {round_entry.get('round')}: conf={round_entry.get('confidence_percent', 'n/a')} validators={round_entry.get('validators_pass', 'n/a')}\n")
    else:
        fh.write("- No rounds recorded\n")

    fh.write("\n## Artifacts\n\n")
    fh.write("- `session.jsonl` (progress events)\n")
    fh.write("- `summary.md` (this file)\n")
    fh.write("- `summary.json` (structured summary)\n")
    fh.write("- `summary.html` (rich summary)\n")
    fh.write("- Per-round traces under `round_*/`\n")

    fh.write("\n_Generated on " + generated_iso + "_\n")

# JSON summary
summary_payload = {
    "session": {
        "id": event.get("session_id"),
        "status": event.get("status"),
        "reason": event.get("reason"),
        "rounds": event.get("rounds"),
        "elapsed_seconds": elapsed,
        "generated_at": generated_iso,
    },
    "question": question,
    "final_answer": final_answer,
    "referee_verdict": event.get("referee_verdict"),
    "numeric_verdict": event.get("numeric_verdict"),
    "parameters": parameters,
    "rounds": rounds,
}
with summary_json_path.open("w", encoding="utf-8") as fh:
    json.dump(summary_payload, fh, indent=2)

# HTML summary
def html_escape(value):
    return html.escape(str(value)) if value is not None else "&mdash;"

html_rows = []
for round_entry in rounds:
    html_rows.append(
        "<tr>"
        f"<td>{html_escape(round_entry.get('round'))}</td>"
        f"<td>{html_escape(round_entry.get('confidence_percent'))}</td>"
        f"<td>{html_escape(round_entry.get('validators_pass'))}</td>"
        f"<td>{html_escape(round_entry.get('referee_verdict'))}</td>"
        f"<td>{html_escape(round_entry.get('final_answer'))}</td>"
        "</tr>"
    )

html_table = "".join(html_rows) or "<tr><td colspan=5>No rounds recorded</td></tr>"

with summary_html_path.open("w", encoding="utf-8") as fh:
    fh.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>MJThinking Summary</title>")
    fh.write("<style>body{font-family:Arial,Helvetica,sans-serif;margin:2rem;}table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ccc;padding:0.5rem;text-align:left;}th{background:#f5f5f5;}</style>")
    fh.write("</head><body>")
    fh.write(f"<h1>MJThinking Session Summary</h1>")
    fh.write("<section>")
    fh.write("<h2>Overview</h2><ul>")
    fh.write(f"<li><strong>Session ID:</strong> {html_escape(event.get('session_id'))}</li>")
    fh.write(f"<li><strong>Status:</strong> {html_escape(event.get('status'))}</li>")
    fh.write(f"<li><strong>Rounds:</strong> {html_escape(event.get('rounds'))}</li>")
    fh.write(f"<li><strong>Elapsed:</strong> {html_escape(format_duration(elapsed))}</li>")
    fh.write(f"<li><strong>Referee Verdict:</strong> {html_escape(event.get('referee_verdict'))}</li>")
    fh.write(f"<li><strong>Numeric Check:</strong> {html_escape(event.get('numeric_verdict'))}</li>")
    reason = event.get("reason")
    if reason:
        fh.write(f"<li><strong>Notes:</strong> {html_escape(reason)}</li>")
    if question:
        fh.write(f"<li><strong>Question:</strong> {html_escape(question)}</li>")
    fh.write("</ul></section>")

    fh.write("<section><h2>Parameters</h2><ul>")
    for key, value in sorted(parameters.items()):
        fh.write(f"<li><code>{html_escape(key)}</code> = {html_escape(value)}</li>")
    fh.write("</ul></section>")

    fh.write("<section><h2>Final Answer</h2>")
    fh.write(f"<pre>{html_escape(final_answer)}</pre>")
    fh.write("</section>")

    fh.write("<section><h2>Rounds</h2><table><thead><tr><th>Round</th><th>Confidence</th><th>Validators</th><th>Referee</th><th>Major Answer</th></tr></thead><tbody>")
    fh.write(html_table)
    fh.write("</tbody></table></section>")

    fh.write(f"<footer><p>Generated on {html_escape(generated_iso)}</p></footer>")
    fh.write("</body></html>")
PY

  STATUS_VALUE="$status" \
  REASON_VALUE="$reason" \
  FINAL_ROUNDS_VALUE="$rounds_value" \
  FINAL_ELAPSED_VALUE="$elapsed_value" \
  FINAL_REF_VER="$RVER" \
  FINAL_NUM_VER="$NVER" \
  FINAL_ANSWER_VALUE="$FA" \
  python3 - <<'PY'
import json, os, pathlib, time

manifest_path = pathlib.Path(os.environ.get("MANIFEST_FILE"))
if manifest_path.is_file():
    with manifest_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
else:
    data = {}

data["completion"] = {
    "status": os.environ.get("STATUS_VALUE"),
    "reason": os.environ.get("REASON_VALUE") or None,
    "rounds": int(os.environ.get("FINAL_ROUNDS_VALUE", "0")),
    "elapsed_seconds": int(os.environ.get("FINAL_ELAPSED_VALUE", "0")),
    "referee_verdict": os.environ.get("FINAL_REF_VER"),
    "numeric_verdict": os.environ.get("FINAL_NUM_VER"),
    "final_answer": os.environ.get("FINAL_ANSWER_VALUE"),
    "timestamp": int(time.time()),
}

with manifest_path.open("w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
PY

  STATUS_STATUS_VALUE="$status" \
  ELAPSED_VALUE="$elapsed_value" \
  FINAL_ROUNDS="$rounds_value" \
  python3 - <<'PY'
import json, os, pathlib, time

path = pathlib.Path(os.environ.get("STATE_FILE"))
data = {
    "session_id": os.environ.get("SESSION_ID"),
    "last_round": int(os.environ.get("FINAL_ROUNDS", "0")),
    "next_round": int(os.environ.get("FINAL_ROUNDS", "0")),
    "next_chains": None,
    "elapsed_seconds": int(os.environ.get("ELAPSED_VALUE", "0")),
    "status": os.environ.get("STATUS_STATUS_VALUE", "completed"),
    "timestamp": int(time.time()),
    "prev_conf_ratio": os.environ.get("FINAL_CONF_RATIO", "0"),
}
with path.open("w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
PY

  local notify_status="Session ${status}"
  local rounds_display="${rounds_value:---}"
  local elapsed_display
  if [ -n "$elapsed_value" ]; then
    elapsed_display=$(format_duration "$elapsed_value")
  else
    elapsed_display="--"
  fi
  local notify_body="Rounds: ${rounds_display} • Elapsed: ${elapsed_display}"
  notify_user "$notify_status" "$notify_body"
}

check_control() {
  while : ; do
    local raw cmd
    raw="$(cat "$CTL_FILE" 2>/dev/null || echo "")"
    cmd="${raw//[[:space:]]/}"
    cmd=${cmd^^}
    case "$cmd" in
      STOP|ABORT)
        if [ "$LAST_CONTROL_STATE" != "STOPPED" ]; then
          log_control_event "control_stop" "$cmd"
          local now elapsed_stop completed_rounds
          now=$(date +%s)
          elapsed_stop=$(( now - START_TS ))
          if (( round > 0 )); then
            completed_rounds=$(( round - 1 ))
          else
            completed_rounds=0
          fi
          log_session_complete "stopped" "Control command $cmd" "$completed_rounds" "$elapsed_stop"
          LAST_CONTROL_STATE="STOPPED"
          echo "[control] Stop requested via $CTL_FILE. Ending session."
        fi
        exit 3
        ;;
      PAUSE)
        if [ "$LAST_CONTROL_STATE" != "PAUSED" ]; then
          log_control_event "control_pause"
          echo "[control] Session paused. Write RESUME to $CTL_FILE to continue."
        fi
        LAST_CONTROL_STATE="PAUSED"
        sleep 5
        continue
        ;;
      RESUME)
        if [ "$LAST_CONTROL_STATE" = "PAUSED" ]; then
          log_control_event "control_resume"
          echo "[control] Session resumed."
        fi
        echo "RUN" > "$CTL_FILE"
        LAST_CONTROL_STATE="RUNNING"
        break
        ;;
      ""|RUN)
        if [ "$LAST_CONTROL_STATE" = "PAUSED" ]; then
          log_control_event "control_resume"
        fi
        LAST_CONTROL_STATE="RUNNING"
        break
        ;;
      *)
        sleep 5
        ;;
    esac
  done
}

while : ; do
  check_control
  run_plugins "pre_round" "$SESSION_DIR" "$round" "$curr_chains"
  echo
  echo "[*] Round $round — running $curr_chains chains…"
  ROUND_DIR="$SESSION_DIR/round_${round}"
  mkdir -p "$ROUND_DIR"
  export MJTHINKING_SESSION_DIR="$SESSION_DIR"
  export MJTHINKING_ROUND_DIR="$ROUND_DIR"

  retries=0
  max_retries=${MJTHINKING_RETRIES:-3}
  backoff=5
  while : ; do
    if "$DIR/mjthinking_core.sh" "$QUESTION" "$curr_chains"; then
      break
    fi
    retries=$((retries+1))
    if (( retries > max_retries )); then
      log_control_event "core_failure" "Round $round failed after $max_retries retries"
      log_session_complete "failed" "Core runner failed after retries" "$((round-1))" "$(( $(date +%s) - START_TS ))"
      notify_user "Session failed" "Round $round core runner aborted after retries"
      exit 4
    fi
    log_control_event "core_retry" "Round $round retry $retries"
    sleep "$backoff"
    backoff=$(( backoff * 2 ))
    if (( backoff > 60 )); then backoff=60; fi
  done

  # Load summary from core runner
  SUMMARY_PATH="$ROUND_DIR/summary.env"
  source "$SUMMARY_PATH" || { echo "[!] No summary found"; exit 2; }
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

  validators_pass="YES"
  validators_output=""
  if [[ -n "$VALIDATOR_HOOKS" ]]; then
    IFS=',' read -r -a validator_names <<< "$VALIDATOR_HOOKS"
    for name in "${validator_names[@]}"; do
      name="${name// /}"
      [[ -z "$name" ]] && continue
      script_path="$VALIDATORS_DIR/$name"
      if [[ -x "$script_path" ]]; then
        HOOK_OUTPUT=$(QUESTION="$QUESTION" ANSWER="$FA" "$script_path" "$QUESTION" "$FA" 2>&1 || true)
        validators_output+="[$name] $HOOK_OUTPUT\n"
        if ! grep -qiE '(PASS|OK|SUCCESS)' <<< "$HOOK_OUTPUT"; then
          validators_pass="NO"
        fi
      else
        validators_output+="[$name] SKIPPED (not executable)\n"
      fi
    done
  fi

  conf_ratio="0"
  conf_percent="0.00"
  if (( TOT > 0 )); then
    ratios_output=$(python3 - <<PY
fc = int(${FC})
tot = int(${TOT})
ratio = fc / tot if tot else 0.0
print(f"{ratio:.6f} {ratio*100:.2f}")
PY
)
    read -r conf_ratio conf_percent <<< "$ratios_output"
  fi
  echo "[*] Confidence ratio: ${conf_percent}%"

  TARGET_CONF_VALUE="$TARGET_CONF"
  CONF_RATIO_VALUE="$conf_ratio"
  target_met=$(python3 - <<PY
import os
def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

conf = to_float(os.environ.get("CONF_RATIO_VALUE"))
target = to_float(os.environ.get("TARGET_CONF_VALUE"))
print("YES" if target > 0 and conf >= target else "NO")
PY
)

  CONF_RATIO_VALUE="$conf_ratio"
  PREV_CONF_RATIO_VALUE="$prev_conf_ratio"
  conf_trend=$(python3 - <<PY
import os

def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

curr = to_float(os.environ.get("CONF_RATIO_VALUE"))
prev = to_float(os.environ.get("PREV_CONF_RATIO_VALUE"))
if curr > prev:
    print("UP")
elif curr < prev:
    print("DOWN")
else:
    print("FLAT")
PY
)

  now=$(date +%s)
  elapsed=$(( now - START_TS ))
  bar=$(progress_bar "$round" "$MAX_ROUNDS")
  eta_seconds=-1
  if (( round > 0 )); then
    per_round=$(( elapsed / round ))
    remaining_rounds=$(( MAX_ROUNDS - round ))
    if (( remaining_rounds > 0 && per_round > 0 )); then
      per_round_est=$per_round
      if (( HISTORY_MEAN_DURATION > 0 )); then
        alpha=$EMA_ALPHA_VALUE
        if (( alpha < 0 )); then alpha=60; fi
        if (( alpha > 100 )); then alpha=100; fi
        per_round_est=$(( (alpha * per_round + (100 - alpha) * HISTORY_MEAN_DURATION) / 100 ))
        if (( per_round_est == 0 )); then per_round_est=$per_round; fi
      fi
      eta_seconds=$(( remaining_rounds * per_round_est ))
    fi
  fi
  if (( eta_seconds >= 0 )); then
    eta_str=$(format_duration "$eta_seconds")
  else
    eta_str="--"
  fi
  elapsed_str=$(format_duration "$elapsed")
  round_duration=$(( elapsed - prev_elapsed_total ))
  if (( round_duration < 0 )); then round_duration=0; fi

  should_print_progress=1
  if (( PROGRESS_UPDATE_INTERVAL > 0 )); then
    if (( last_progress_print > 0 && now - last_progress_print < PROGRESS_UPDATE_INTERVAL )); then
      should_print_progress=0
    else
      last_progress_print=$now
    fi
  fi
  if (( should_print_progress )); then
    if [[ -n "${TIME_BUDGET:-}" && "$TIME_BUDGET" -gt 0 ]]; then
      tbar=$(time_progress_bar "$elapsed" "$TIME_BUDGET" 28)
      echo "[progress] $tbar | rounds=$bar | elapsed=$elapsed_str | eta~$eta_str"
    else
      echo "[progress] $bar | elapsed=$elapsed_str | eta~$eta_str"
    fi
  fi

  ROUND_TS=$(date +%s)
  {
    printf 'ROUND_COMPLETED_TS=%s\n' "$ROUND_TS"
    printf 'ROUND_DURATION=%s\n' "$round_duration"
  } >> "$SUMMARY_PATH"
  cp "$SUMMARY_PATH" "$SESSION_DIR/summary_round_${round}.env" 2>/dev/null || true

  printf '%s\n' "$FA" > "$SESSION_DIR/round_${round}_best.txt"
  ROUND_JSON_META=$(ROUND="$round" FINAL_ANSWER="$FA" FINAL_COUNT="$FC" TOTAL_CHAINS="$TOT" ROUND_TS="$ROUND_TS" ROUND_DURATION="$round_duration" VALIDATORS_PASS="$validators_pass" python3 - <<'PY'
import json, os

payload = {
    "round": int(os.environ.get("ROUND", "0")),
    "final_answer": os.environ.get("FINAL_ANSWER"),
    "majority_count": int(os.environ.get("FINAL_COUNT", "0")),
    "total_chains": int(os.environ.get("TOTAL_CHAINS", "0")),
    "timestamp": int(os.environ.get("ROUND_TS", "0")),
    "round_duration": int(os.environ.get("ROUND_DURATION", "0")),
    "validators_pass": os.environ.get("VALIDATORS_PASS"),
}
print(json.dumps(payload, indent=2))
PY
)
  printf '%s\n' "$ROUND_JSON_META" > "$SESSION_DIR/round_${round}_snapshot.json"

  ROUND="$round" \
  ROUND_TS="$ROUND_TS" \
  ROUND_DURATION="$round_duration" \
  ELAPSED="$elapsed" \
  ETA_VALUE="$eta_seconds" \
  MAJ_COUNT="$FC" \
  TOTAL_CHAINS_VALUE="$TOT" \
  REF_VER="$RVER" \
  NUM_VER="$NVER" \
  FINAL_ANSWER_VALUE="$FA" \
  VALIDATORS_PASS="$validators_pass" \
  CONF_RATIO="$conf_ratio" \
  CONF_PERCENT="$conf_percent" \
  TARGET_MET="$target_met" \
  CONF_TREND="$conf_trend" \
  MANIFEST_FILE="$MANIFEST_FILE" \
  python3 - <<'PY'
import json, os, pathlib

path = pathlib.Path(os.environ.get("MANIFEST_FILE"))
if path.is_file():
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
else:
    data = {"rounds": []}

round_entry = {
    "round": int(os.environ.get("ROUND", "0")),
    "timestamp": int(os.environ.get("ROUND_TS", "0")),
    "round_duration": int(os.environ.get("ROUND_DURATION", "0")),
    "elapsed_seconds": int(os.environ.get("ELAPSED", "0")),
    "eta_seconds": int(os.environ.get("ETA_VALUE", "-1")),
    "majority_count": int(os.environ.get("MAJ_COUNT", "0")),
    "total_chains": int(os.environ.get("TOTAL_CHAINS_VALUE", "0")),
    "referee_verdict": os.environ.get("REF_VER"),
    "numeric_verdict": os.environ.get("NUM_VER"),
    "final_answer": os.environ.get("FINAL_ANSWER_VALUE"),
    "validators_pass": os.environ.get("VALIDATORS_PASS"),
}

data.setdefault("rounds", []).append(round_entry)

with path.open("w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
PY

  ROUND="$round" \
  CURR_CHAINS="$curr_chains" \
  MAJ_COUNT="$FC" \
  MAJ_TOTAL="$TOT" \
  MAJ_REQ="$maj_req" \
  PASS_MAJ="$pass_majority" \
  REF_VER="$RVER" \
  PASS_REF="$pass_ref" \
  NUM_VER="$NVER" \
  PASS_NUM="$pass_numeric" \
  ELAPSED="$elapsed" \
  ETA="$eta_seconds" \
  ROUND_TS="$ROUND_TS" \
  ROUND_DURATION="$round_duration" \
  VALIDATORS_PASS="$validators_pass" \
  CONF_RATIO="$conf_ratio" \
  CONF_PERCENT="$conf_percent" \
  TARGET_MET="$target_met" \
  CONF_TREND="$conf_trend" \
  ROUND_JSON=$(python3 - <<'PY'
import json, os, time

def as_int(name, default=0):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default

payload = {
    "event": "round_complete",
    "session_id": os.environ.get("SESSION_ID"),
    "round": as_int("ROUND"),
    "chains": as_int("CURR_CHAINS"),
    "majority_count": as_int("MAJ_COUNT"),
    "majority_total": as_int("MAJ_TOTAL"),
    "majority_required": as_int("MAJ_REQ"),
    "majority_pass": os.environ.get("PASS_MAJ", "NO"),
    "referee_verdict": os.environ.get("REF_VER", "UNKNOWN"),
    "referee_pass": os.environ.get("PASS_REF", "NO"),
    "numeric_verdict": os.environ.get("NUM_VER", "UNKNOWN"),
    "numeric_pass": os.environ.get("PASS_NUM", "NO"),
    "validators_pass": os.environ.get("VALIDATORS_PASS", "YES"),
    "elapsed_seconds": as_int("ELAPSED"),
    "eta_seconds": as_int("ETA"),
    "timestamp": as_int("ROUND_TS", int(time.time())),
    "round_duration": as_int("ROUND_DURATION"),
}
print(json.dumps(payload))
PY
  )
  append_event "$ROUND_JSON"
  run_plugins "post_round" "$SESSION_DIR" "$round" "$FA" "$conf_ratio" "$validators_pass"

  HISTORY_JSON="$ROUND_JSON" \
  HISTORY_FILE="$ROUND_HISTORY_FILE" \
  python3 - <<'PY'
import json, os

payload = json.loads(os.environ.get("HISTORY_JSON", "{}"))
history_path = os.environ.get("HISTORY_FILE")
if history_path:
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    with open(history_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")
PY

  if [ "$pass_majority" = "YES" ] && [ "$pass_ref" = "YES" ]; then
    FA="$FA" \
    RVER="$RVER" \
    NVER="$NVER" \
    ELAPSED="$elapsed" \
    log_session_complete "success"
    echo
    echo "================== MJThinking RESULT =================="
    echo "Final Answer: $FA"
    echo "(Majority $FC/$TOT • Referee PASS • Numeric $NVER)"
    echo "All traces under: $DIR/runs/"
    echo "====================================================="
    exit 0
  fi

  if [ "$round" -ge "$MAX_ROUNDS" ]; then
    FA="$FA" \
    RVER="$RVER" \
    NVER="$NVER" \
    ROUND="$round" \
    ELAPSED="$elapsed" \
    log_session_complete "best_effort" "Reached MAX_ROUNDS"
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
  prev_conf_ratio="$conf_ratio"
  prev_elapsed_total=$elapsed
done
