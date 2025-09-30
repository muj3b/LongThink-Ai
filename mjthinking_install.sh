#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---- 0) Tunables (safe defaults for an ~18 GB RAM Mac; override by exporting before run) ----
MODEL="${MODEL:-deepseek-r1:7b}"   # small reasoning model available via Ollama library
CTX="${CTX:-4096}"                 # context tokens (bump to 8192 if you like)
TEMP="${TEMP:-0.8}"                # sampling temperature
TOP_P="${TOP_P:-0.95}"             # nucleus sampling
PREDICT="${PREDICT:-900}"          # max new tokens per chain (raise to think longer per chain)
CHAINS="${CHAINS:-10}"             # parallel chains (raise to think longer overall)
MAJ_MIN="${MAJ_MIN:-0.5}"          # min majority fraction to accept (0.5 = simple majority)
MAX_ROUNDS="${MAX_ROUNDS:-3}"      # escalation rounds (doubles chains if weak/conflict)
WORKDIR="${WORKDIR:-$SCRIPT_DIR}"
PORT="${PORT:-11434}"

# ---- 1) Dependency Installation ----
# This function will install packages using the available package manager.
install_deps() {
    local pkg_manager=""
    if command -v apt-get >/dev/null 2>&1; then
        pkg_manager="apt-get"
    elif command -v yum >/dev/null 2>&1; then
        pkg_manager="yum"
    elif command -v brew >/dev/null 2>&1; then
        pkg_manager="brew"
    fi

    if [[ -z "$pkg_manager" ]]; then
        echo "[!] No supported package manager (apt-get, yum, brew) found. Please install jq and python3 manually." >&2
        # On failure, check if they are already installed.
        if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
            exit 1
        fi
        return
    fi

    echo "[*] Using package manager: $pkg_manager"

    if ! command -v jq >/dev/null 2>&1; then
        echo "[*] Installing jq…"
        case "$pkg_manager" in
            apt-get) sudo apt-get install -y jq ;;
            yum)     sudo yum install -y jq ;;
            brew)    brew install jq ;;
        esac
    else
        echo "[*] jq is already installed."
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        echo "[*] Installing python3…"
        case "$pkg_manager" in
            apt-get) sudo apt-get install -y python3 ;;
            yum)     sudo yum install -y python3 ;;
            brew)    brew install python ;;
        esac
    else
        echo "[*] python3 is already installed."
    fi
}


# On macOS, ensure Homebrew is installed first.
if [[ "$(uname)" == "Darwin" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "[*] Homebrew missing on macOS; installing…"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
fi

install_deps

# ---- 2) Ensure Ollama CLI/server ----
if ! command -v ollama >/dev/null 2>&1; then
  echo "[*] Installing Ollama…"
  # The official install script is the most portable method.
  curl -fsSL https://ollama.com/install.sh | sh
fi

# ---- 3) Start Ollama only if not already up ----
API="http://127.0.0.1:${PORT}"
if ! curl -s "${API}/api/tags" >/dev/null 2>&1; then
  echo "[*] Starting ollama server…"
  # Ensure no old instances are running
  pkill -f "ollama serve" >/dev/null 2>&1 || true
  # Start the server in the background
  ollama serve >/tmp/ollama.log 2>&1 &
  # Wait for the API to become available
  echo -n "[*] Waiting for ${API} ..."
  until curl -s "${API}/api/tags" >/dev/null 2>&1; do printf "."; sleep 1; done
  echo " up"
else
  echo "[*] Ollama server already running."
fi

# ---- 4) Pull the model (no-op if already present) ----
echo "[*] Pulling $MODEL (first time may download several GBs; otherwise quick)…"
ollama pull "$MODEL"

# ---- 5) Workspace and templates ----
mkdir -p "$WORKDIR/runs"
cd "$WORKDIR"

# main reasoning prompt (forces a one-line 'Final Answer:' for voting)
cat > prompt_template.txt <<'TXT'
You are a careful, rigorous reasoner. Work step by step with explicit intermediate reasoning.
Check your result independently before finalizing. If math/code is involved, verify it logically.

CRITICAL: End with exactly one line:
Final Answer: <one line only>
TXT

# "referee" prompt that re-derives the solution and judges the candidate
cat > referee_prompt.txt <<'TXT'
You are a strict verifier. Re-derive from scratch (do not reuse the candidate's derivation).
Then judge the candidate's Final Answer.

Rules:
1) Give a short independent derivation or calculation.
2) If your independently derived final answer equals the candidate's, output:
VERDICT: PASS
Otherwise output:
VERDICT: FAIL
3) If FAIL, briefly explain why.

Return your reasoning first (brief), then the VERDICT line.
TXT

# ---- 6) MJThinking core runner via Ollama REST API ----
# This version uses MJTHINKING_ROUND_DIR to isolate round artifacts.
cat > mjthinking_core.sh <<'BASH'
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
# This complex sed chain is a candidate for future refactoring.
grep -h "Final Answer:" "$RUNS_DIR"/*.txt | sed -E 's/.*Final Answer:[[:space:]]*//' | sed -E 's/[[:space:]]+$//' \
  | sed -E 's/^\\*\\*([^*]+)\\*\\*$/\\1/' \
  | sed -E 's/^\\\\boxed\\{(.*)\\}$/\\1/' \
  | sed -E 's/^\\$([^$]*)\\$$/\\1/' \
  | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' \
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
BASH
chmod +x mjthinking_core.sh

# ---- 7) Referee verifier (independent re-derivation + PASS/FAIL) ----
# This version uses MJTHINKING_ROUND_DIR to save its output.
cat > referee.sh <<'BASH'
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

# Use round-specific directory if provided by orchestrator
ROUND_DIR="${MJTHINKING_ROUND_DIR:-$DIR/runs}"
mkdir -p "$ROUND_DIR"
echo "$TEXT" > "$ROUND_DIR/referee.txt"

# Extract VERDICT line
VERDICT="$(printf "%s\n" "$TEXT" | grep -E '^\s*VERDICT:\s*(PASS|FAIL)\s*$' | tail -n 1 | awk -F: '{print $2}' | tr -d '[:space:]')"
[ -z "$VERDICT" ] && VERDICT="UNKNOWN"

echo "VERDICT=$VERDICT"
BASH
chmod +x referee.sh

# ---- 8) Optional numeric checker (safe arithmetic only) ----
cat > arith_eval.py <<'PY'
import ast, math, re, sys

def safe_eval(expr: str):
    # Allow only numbers, operators, parens, and whitespace.
    # This is still not perfectly safe, but better.
    expr = expr.strip()
    if not re.fullmatch(r"[\d\s\.\+\-\*\/\%\(\)]+", expr):
        raise ValueError("Unsafe characters in expression")

    # Replace dangerous patterns
    if "__" in expr:
        raise ValueError("Double underscores are not allowed")

    # Use ast to parse and validate the expression
    tree = ast.parse(expr, mode='eval')
    allowed_nodes = {
        ast.Expression, ast.Constant, ast.Num, ast.BinOp, ast.UnaryOp,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Load
    }
    for node in ast.walk(tree):
        if type(node) not in allowed_nodes:
            raise ValueError(f"Disallowed operation: {type(node).__name__}")

    # The 'math' module is provided for functions like sqrt, etc.
    # The environment is cleared of builtins.
    return eval(compile(tree, "<string>", "eval"), {"__builtins__": {}, "math": math})

def extract_numeric(s: str):
    # Improved regex to find numbers, including scientific notation.
    # It prioritizes numbers at the end of the string.
    matches = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except (ValueError, IndexError):
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("UNKNOWN")
        sys.exit(0)

    question, candidate_answer = sys.argv[1], sys.argv[2]

    # Try to find a simple arithmetic expression in the question.
    # This is a weak spot, as questions can be complex.
    # "what is 4 * (2+3)" -> "4*(2+3)"
    expr_in_question = "".join(c for c in question if c in "0123456789.+-*/()% ")

    try:
        expected_value = safe_eval(expr_in_question)
    except Exception:
        print("UNKNOWN")
        sys.exit(0)

    actual_value = extract_numeric(candidate_answer)
    if actual_value is None:
        print("UNKNOWN")
        sys.exit(0)

    # Use a relative tolerance for floating point comparisons
    if math.isclose(expected_value, actual_value, rel_tol=1e-6, abs_tol=1e-9):
        print("PASS")
    else:
        print("FAIL")
PY

# ---- 9) MJThinking orchestrator: BoN → Referee → (optional) Numeric → Escalate ----
# This version creates session- and round-specific directories for clean audit trails.
cat > mjthinking.sh <<'BASH'
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
BASH
chmod +x mjthinking.sh

# ---- 10) Smoke test (Ctrl+C to skip) ----
echo "[*] Quick smoke test (simple arithmetic)…"
./mjthinking.sh "What is 37*29? Show your work."

echo
echo "[OK] Setup complete."
echo "Use it like:"
echo "  $WORKDIR/mjthinking.sh \"Prove or disprove: f(x)=x^x is convex on (0,∞). Give final conclusion.\""
echo "  (set CHAINS=20 or 40 to 'think' longer; raise PREDICT for longer chains)"