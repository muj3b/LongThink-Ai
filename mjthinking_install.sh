# === WARP ONE-PASTE: MJTHINKING (Best-of-N + Referee + Escalation) ===
# Safe & idempotent. Installs only if missing. Saves all traces.
# Verified against:
# - Ollama API /api/generate + stream:false + options (num_ctx, temperature, top_p, num_predict, seed)
# - Homebrew path/prefix
# - deepseek-r1 availability in Ollama library

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

# ---- 1) Ensure Homebrew (don’t reinstall if present) ----
if ! command -v brew >/dev/null 2>&1; then
  echo "[*] Homebrew missing; installing…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -d "/opt/homebrew/bin" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
  elif [ -d "/usr/local/bin" ]; then
    export PATH="/usr/local/bin:$PATH"
  fi
else
  # Make sure brew is on PATH for Apple Silicon
  if [ -d "/opt/homebrew/bin" ] && ! echo "$PATH" | grep -q "/opt/homebrew/bin"; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi

# ---- 2) Ensure jq and python3 (install only if missing) ----
if ! command -v jq >/dev/null 2>&1; then
  echo "[*] Installing jq…"
  brew install jq
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[*] Installing python3…"
  brew install python
fi

# ---- 3) Ensure Ollama CLI/server (formula first; fall back to cask) ----
if ! command -v ollama >/dev/null 2>&1; then
  echo "[*] Installing Ollama…"
  brew install ollama || brew install --cask ollama
fi

# ---- 4) Start Ollama only if not already up ----
API="http://127.0.0.1:${PORT}"
if ! curl -s "${API}/api/tags" >/dev/null 2>&1; then
  echo "[*] Starting ollama server…"
  pkill -f "ollama serve" >/dev/null 2>&1 || true
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  echo -n "[*] Waiting for ${API} ..."
  until curl -s "${API}/api/tags" >/dev/null 2>&1; do printf "."; sleep 1; done
  echo " up"
else
  echo "[*] Ollama server already running."
fi

# ---- 5) Pull the model (no-op if already present) ----
echo "[*] Pulling $MODEL (first time downloads GBs; otherwise quick)…"
ollama pull "$MODEL"

# ---- 6) Workspace and templates ----
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

# ---- 7) MJThinking core runner via Ollama REST API ----
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
RUNS_DIR="$DIR/runs"

mkdir -p "$RUNS_DIR"
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
BASH
chmod +x mjthinking_core.sh

# ---- 8) Referee verifier (independent re-derivation + PASS/FAIL) ----
cat > referee.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

QUESTION="${1:-}"
CANDIDATE="${2:-}"
[ -z "$QUESTION" ] && { echo "Usage: $0 \"QUESTION\" \"CANDIDATE_FINAL_ANSWER\""; exit 1; }

MODEL="${MODEL:-deepseek-r1:7b}"
CTX="${CTX:-4096}"
TEMP="${TEMP:-0.2}"      # low temp for verifier stability
TOP_P="${TOP_P:-0.9}"
PREDICT="${PREDICT:-600}"
API="${API:-http://127.0.0.1:11434}"

REFP="$(cat referee_prompt.txt)

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

echo "$TEXT" > "runs/referee.txt"

# Extract VERDICT line
VERDICT="$(printf "%s\n" "$TEXT" | grep -E '^\s*VERDICT:\s*(PASS|FAIL)\s*$' | tail -n 1 | awk -F: '{print $2}' | tr -d '[:space:]')"
[ -z "$VERDICT" ] && VERDICT="UNKNOWN"

echo "VERDICT=$VERDICT"
BASH
chmod +x referee.sh

# ---- 9) Optional numeric checker (safe arithmetic only) ----
cat > arith_eval.py <<'PY'
import ast, math, re, sys

def safe_eval(expr: str):
    # allow only numbers, + - * / // % ** ( ) . , and whitespace
    if not re.fullmatch(r"[0-9\.\s\+\-\*\/\%\(\)\,]+", expr):
        raise ValueError("unsafe chars")
    node = ast.parse(expr, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
               ast.Pow, ast.USub, ast.UAdd, ast.Tuple)
    for n in ast.walk(node):
        if not isinstance(n, allowed):
            raise ValueError("bad node")
    return eval(compile(node, "<expr>", "eval"), {"__builtins__": {}}, {"math": math})

def extract_numeric(s: str):
    # pick last numeric token in the final answer line
    m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
    if not m: return None
    return float(m[-1])

if __name__ == "__main__":
    # argv: question  candidate_final_line
    if len(sys.argv) < 3:
        print("UNKNOWN")
        sys.exit(0)

    q, cand = sys.argv[1], sys.argv[2]
    # Try to find a simple arithmetic expression in the question
    qexpr = "".join(ch for ch in q if ch in "0123456789.+-*/()% ,")
    try:
        qexpr_val = safe_eval(qexpr)
    except Exception:
        print("UNKNOWN"); sys.exit(0)

    ans = extract_numeric(cand)
    if ans is None:
        print("UNKNOWN"); sys.exit(0)

    # Loose numeric match tolerance
    if abs(qexpr_val - ans) <= max(1e-9, 1e-6*abs(qexpr_val)):
        print("PASS")
    else:
        print("FAIL")
PY

# ---- 10) MJThinking orchestrator: BoN → Referee → (optional) Numeric → Escalate ----
cat > mjthinking.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

QUESTION="${1:-}"
[ -z "$QUESTION" ] && { echo "Usage: $0 \"YOUR QUESTION\""; exit 1; }

CHAINS="${CHAINS:-10}"
MAJ_MIN="${MAJ_MIN:-0.5}"   # e.g., 0.5 requires simple majority
MAX_ROUNDS="${MAX_ROUNDS:-3}"

round=1
curr_chains="$CHAINS"

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
  pass_ref=$([ "$RVER" = "PASS" ] && echo YES || echo NO)
  pass_numeric=$([ "$NVER" = "PASS" ] && echo YES || echo NO)

  if [ "$pass_majority" = "YES" ] && [ "$pass_ref" = "YES" ]; then
    echo
    echo "================== MJTHINKING RESULT =================="
    echo "Final Answer: $FA"
    echo "(Majority $FC/$TOT • Referee PASS • Numeric $NVER)"
    echo "All traces under: $DIR/runs/"
    echo "====================================================="
    exit 0
  fi

  if [ "$round" -ge "$MAX_ROUNDS" ]; then
    echo
    echo "================== MJTHINKING (BEST EFFORT) ========="
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
BASH
chmod +x mjthinking.sh

# ---- 11) Smoke test (Ctrl+C to skip) ----
echo "[*] Quick smoke test (simple arithmetic)…"
./mjthinking.sh "What is 37*29? Show your work."

echo
echo "[OK] Setup complete."
echo "Use it like:"
echo "  $WORKDIR/mjthinking.sh \"Prove or disprove: f(x)=x^x is convex on (0,∞). Give final conclusion.\""
echo "  (set CHAINS=20 or 40 to 'think' longer; raise PREDICT for longer chains)"
