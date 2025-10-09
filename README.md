# 🧠 MJThinking Reasoning Platform

![Status](https://img.shields.io/badge/status-experimental-blue)
![Language](https://img.shields.io/badge/python-3.11%2B-3776AB)
![API](https://img.shields.io/badge/API-Ollama-green)
![Research](https://img.shields.io/badge/backed_by-2024_studies-gold)

<div align="center">

**Transform small, local AI models into deep-reasoning powerhouses.**  
MJThinking lets 7B–14B models think for 30–120+ minutes so they can reach answers that typically demand much larger checkpoints.  
**Quick Start • Architecture • Usage • Configuration**

</div>

> **Quick take:** MJThinking trades *time* for *quality*. Instead of purchasing bigger models, you orchestrate longer, supervised reasoning sessions while keeping everything on local hardware and logging every trace.

## 🔬 The Science Behind Extended Reasoning

> [!NOTE]
> **Yes, it actually works.** Recent 2024 research validates this approach.

### 📊 Research Foundation

**What makes MJThinking legit:**
- **Test-time compute scaling** is more effective than scaling model parameters
- **Small language models can outperform larger models** when applying compute-optimal test-time scaling methods
- Models **learn to leverage more test-time compute** to solve harder problems

### 🔧 How It Increases Reasoning Time

| Technique | Implementation | Research Basis |
|-----------|----------------|----------------|
| **🎯 Best-of-N Sampling** | Sample N outputs in parallel and select the highest-scoring | Proven to significantly improve LM performance |
| **🌳 Tree-of-Thought Planning** | Generate, expand, and evaluate solution plans | Structured exploration prevents collapse into weak answers |
| **✅ Verification Layers** | Multi-stage validation with referee models | Quality gates ensure consensus before accepting results |

### 🎯 What Makes This Unique?

> [!IMPORTANT]
> **MJThinking combines proven techniques into a complete production system.**

- **Individual techniques exist** in research papers
- **Academic experiments** focus on single methods
- **MJThinking orchestrates everything** into a local, production-ready platform
- **The trade-off:** Additional computational cost at inference for improved output quality

**Bottom line:** It's not just "thinking longer" - it's **structured exploration with verification**, backed by 2024 research.

---

## Table of Contents

- **[🎯 The Big Idea](#-the-big-idea)**
- **[🎪 Session Playbook](#-session-playbook)**
- **[🏗️ Architecture](#️-architecture)**
- **[📚 Component Ecosystem](#-component-ecosystem)**
- **[🚀 Quick Start](#-quick-start)**
- **[💫 Usage Patterns](#-usage-patterns)**
- **[🛡️ Execution Modes](#️-execution-modes)**
- **[⚙️ Configuration](#️-configuration)**
- **[📊 Performance Guide](#-performance-guide)**
- **[🔍 Observability & Debugging](#-observability--debugging)**
- **[🚀 Advanced Usage](#-advanced-usage)**
- **[🛠️ Development & Extension](#️-development--extension)**
- **[📖 FAQ](#-faq)**

## 🎯 The Big Idea

> [!SUMMARY]
> Give small models hours to think with structure, and they close much of the gap to frontier systems.

Large frontier models compress lengthy internal reasoning into quick responses. MJThinking flips the equation: **let a small model deliberate for a long time with explicit supervision** and enforce quality gates before accepting an answer.

- **Time ↔ Quality:** Spend minutes instead of buying bigger checkpoints.
- **Local ↔ Cloud:** Everything runs on your workstation via the Ollama API.
- **Small ↔ Large:** Coax 7B models into producing 70B-class reasoning by sustaining the chain of thought.

### Why long thinking works

- **Structured exploration:** Iterative waves, plan expansions, and voting prevent collapse into weak first answers.
- **Verification loop:** Referee models and numeric checks gatekeep consensus.
- **Full transparency:** Every prompt, response, verdict, and vote is archived under `runs/` for post-mortems.

### Tuning Philosophy

- **Time budget:** More minutes yields richer reasoning but keeps GPUs busy.
- **Confidence threshold (`CONF`):** Raise it to demand stronger consensus before returning results.
- **Fallback models:** Smoothly escalate from 7B to 14B (or beyond) when waves stagnate.

### 🎪 Session Playbook

| Session | Runner | Core Settings | Duration | Best For |
| --- | --- | --- | --- | --- |
| 🚀 **Quick Check** | `mjthinking.sh` | `CHAINS=8`, `PREDICT=600`, `TIME_BUDGET=180` | 1–2 minutes | Environment sanity check & baselines |
| ⚖️ **Extended Think** | `mjthinking_ultra.py` | `MODE=HYBRID`, `TIME_BUDGET=3600`, `PLANS=4`, `EXPAND=3` | 35–75 minutes | 7B → 14B-quality deep dives |
| 🏃‍♂️ **Marathon** | `mjthinking_ultra7b.py` | `TIME_BUDGET=7200`, `BATCH=16`, `PREDICT=1800` | 90–150 minutes | Research-grade or open-ended work |

> [!IMPORTANT]
> Long sessions benefit from `TEMP≈0.6`, `MODEL_FALLBACK` pointing to a stronger checkpoint, and vigilant GPU temperature monitoring.

## 🏗️ Architecture

```mermaid
graph TB
    A[🤔 User Question] --> B[🎭 MJThinking Orchestrator]

    subgraph BON[🎯 Best-of-N Sampling]
        C[📝 Parallel Chains]
        D[🗳️ Consensus Voting]
    end

    subgraph TOT[🌳 Tree-of-Thought]
        E[📋 Plan Generation]
        F[🔄 Plan Expansion]
        G[⭐ Plan Evaluation]
    end

    subgraph VERIFY[✅ Verification Layer]
        H[👨‍⚖️ Referee Check]
        I[🔢 Arithmetic Validation]
    end

    B --> C
    B --> E
    C --> D
    E --> F
    F --> G
    D --> H
    G --> H
    H --> I
    I --> J[📁 Audit Trail (runs/)]
```

## 📚 Component Ecosystem

### 🎮 Main Controllers

| Component | Purpose | When to Use |
| --- | --- | --- |
| `mjthinking.sh` | 🔄 Escalating Best-of-N orchestrator | Fast multi-round majority votes with referee gating |
| `mjthinking_pro.py` | 🐍 Multithreaded Python controller | Balanced latency with weighting, fallback model support |
| `mjthinking_ultra.py` | 🚀 Hybrid BON/TOT orchestrator | Maximum flexibility; alternate between modes per wave |
| `mjthinking_ultra7b.py` | 🎯 7B-optimized long-context runner | Marathon reasoning on modest hardware (CTX 8192) |

### 🛠️ Core Utilities

| Tool | Function | When to Use |
| --- | --- | --- |
| `mjthinking_core.sh` | Parallel chain launcher | Building block for Best-of-N rounds |
| `referee.sh` | Answer verification via `referee_prompt.txt` | Independent PASS/FAIL judgement |
| `arith_eval.py` | Numeric validation | Quick arithmetic cross-checking |
| `validators/` + `VALIDATOR_HOOKS` | Custom confidence validators executed each round | Augment referee decisions with domain-specific checks |
| `mjthinking_enqueue.py` | Queue jobs into `runs/queue.jsonl` | Batch prompts for background execution |
| `mjthinking_worker.py` | Dequeue & process jobs | Hands-free batch processing with logging |
| `mjthinking_gc.sh` | Session garbage collector | Reclaim disk space by age/keep-count/explicit IDs |
| `mjthinking_api.py` | FastAPI control plane (launch streams/status) | Integrate with dashboards & custom tooling |
| `web/` | Static dashboard consuming the API | Quick web view for session status |
| `plugins/` | Hook scripts triggered during runs | Extend behavior without modifying core scripts |

### 📋 Prompt Templates

| Template | Controls | Customization |
| --- | --- | --- |
| `prompts/default.txt` (set via `PROMPT_STYLE=default`) | Core reasoning scaffold & final-line contract | 🔧 Essential |
| `prompts/<style>.txt` | Style-specific reasoning scaffolds | 🎨 Swap in domain voices (math, finance, debugging, etc.) |
| `referee_prompt.txt` | Verification instructions | 🔧 Essential |
| `tot_plan_prompt.txt` / `tot_attempt_prompt.txt` / `tot_evaluate_prompt.txt` | Tree-of-Thought workflow | 🎨 Advanced |

## 🚀 Quick Start

1. **Install prerequisites & scripts**

   ```bash
   bash mjthinking_install.sh
   ```

2. **Verify the pipeline end-to-end**

   ```bash
   ./mjthinking.sh "What is 37 × 29?"
   ```

3. **Resume an interrupted session**

   ```bash
   ./mjthinking.sh --resume mjthinking_20240908_123456_42
   ```

3. **Launch your first deep-think session**

   ```bash
   MODEL=google/gemma-3-12b TIME_BUDGET=1800 \
   python3 mjthinking_ultra.py "Prove that the square root of 2 is irrational."
   ```
   > The CLI now streams a live progress bar with ETA estimates and writes every wave to `runs/<session_id>/session.jsonl`, so you can resume, monitor, or audit long (2h+) sessions without guesswork.
   >
   > Leave `TIME_BUDGET` unset (or set to `auto`) to let MJThinking size the budget to your question; short prompts finish in minutes, proofs/research prompts expand toward the 2 h ceiling. Override with an explicit second count when you need a fixed cap.

## 💫 Usage Patterns

### 🎯 Quick Verification (1–2 minutes)

```bash
CHAINS=8 PREDICT=600 ./mjthinking.sh "Explain the quicksort algorithm."
```

### ⚡ Balanced Reasoning (5–10 minutes)

```bash
MODEL=google/gemma-3-12b MODEL_FALLBACK=google/gemma-3-27b \
CONF=0.7 python3 mjthinking_pro.py "Design a distributed hash table."
```

### 🏃‍♂️ Extended Deep Think (30–60 minutes)

```bash
TIME_BUDGET=3600 MODE=HYBRID BATCH=16 \
python3 mjthinking_ultra.py "Compare quantum vs classical complexity classes."
```

### 🌙 Background Processing (2–4 hours)

```bash
TIME_BUDGET=7200 MODE=HYBRID ./mjthinking_run7b_bg.sh \
"Analyze the Byzantine Generals problem and propose novel solutions."

./monitor7b.sh   # Tail latest background log
./last_answer7b.sh   # Fetch most recent Final Answer
```

## 🛡️ Execution Modes

<details>
<summary><strong>🎯 Best-of-N (BON)</strong></summary>

- Launch multiple parallel reasoning chains.
- Canonicalize `Final Answer:` lines and tally weighted votes.
- Require referee PASS before returning an answer.
- **Best for:** math, logic, and crisp questions with clear consensus.

</details>

<details>
<summary><strong>🌳 Tree-of-Thought (TOT)</strong></summary>

- Generate structured solution plans (`PLANS`).
- Expand each plan multiple times (`EXPAND`).
- Score plan quality via JSON feedback, then vote on final answers.
- **Best for:** creative ideation, multi-step derivations, research prompts.

</details>

<details>
<summary><strong>🔀 Hybrid Mode</strong></summary>

- Alternate between BON and TOT waves.
- Adapt strategy based on convergence speed and verification outcomes.
- Combine breadth (BON) with depth (TOT) automatically.
- **Best for:** unknown task types or when you need maximum quality.

</details>

## ⚙️ Configuration

### 🎛️ Essential Settings

| Variable | Default | Purpose | Tuning Tips |
| --- | --- | --- | --- |
| `MODEL` | `google/gemma-3-12b` | Primary reasoning model | Point at any local or hosted checkpoint (`MODEL=my/model:tag`) |
| `MODEL_FALLBACK` | _(empty)_ | Secondary model if consensus stalls | e.g. `google/gemma-3-27b` or any heavier backup model |
| `API` | `http://127.0.0.1:11434` | Inference endpoint base URL | Use Ollama default or switch to `http://127.0.0.1:1234` (LM Studio) / custom hosts |
| `API_TYPE` | `auto` | API dialect (`ollama` vs `openai`) | Leave unset for auto-detect; force `openai` for LM Studio / OpenAI-compatible servers |
| `API_KEY` / `OPENAI_API_KEY` | _(empty)_ | Optional bearer token for `API_TYPE=openai` | Set when your server enforces authentication |
| `TIME_BUDGET` | `auto` | Max wall-clock seconds | Leave on `auto` to adapt to prompt complexity; set explicit seconds when you need a hard cap |
| `TIME_BUDGET_DEFAULT` | `1800` (Pro) / `3600` (Ultra7B) | Baseline when `TIME_BUDGET=auto` | Raise/lower to bias adaptive runs longer or shorter globally |
| `TIME_BUDGET_MIN` / `TIME_BUDGET_MAX` | `300 / 7200` (Pro), `600 / 10800` (Ultra7B) | Bounds for adaptive timing | Tighten to keep sessions within resource or SLO constraints |
| `BATCH` / `CHAINS` | `12` / `10` | Parallel chains per wave/round | Balance throughput vs VRAM and API load |
| `CONF` | `0.66` | Weighted confidence threshold | Raise for stricter consensus |
| `MJTHINKING_WEBHOOK_URL` | _(empty)_ | Optional HTTP endpoint to receive JSON progress events | Point to Slack/Discord/web dashboards; omit to disable |
| `MJTHINKING_WEBHOOK_TIMEOUT` | `2` | Seconds before webhook POST times out | Increase for slow endpoints |
| `MJTHINKING_NOTIFY` | _(empty)_ | Enable macOS desktop notifications when set (any non-empty value) | Uses `osascript`; ignored when unset |
| `MJTHINKING_RETRIES` | `3` | Automatic retries per round when `mjthinking_core.sh` fails | Backoff starts at 5s and doubles up to 60s |

### 🎨 Advanced Tuning

<details>
<summary><strong>🔧 Performance Optimization</strong></summary>

```bash
# Fast iterations (30–60 seconds)
PREDICT=400 CHAINS=6 CONF=0.5

# Balanced quality (2–5 minutes)
PREDICT=900 CHAINS=12 CONF=0.66

# Maximum depth (10+ minutes)
PREDICT=1600 CHAINS=16 CONF=0.8 TIME_BUDGET=1800
```

</details>

<details>
<summary><strong>🌳 Tree-of-Thought Tuning</strong></summary>

```bash
# More exploration
PLANS=5 EXPAND=3

# Focused search
PLANS=3 EXPAND=2

# Quick TOT smoke test
PLANS=2 EXPAND=1
```

</details>

## 📊 Performance Guide

### ⏱️ Expected Runtimes

| Session Type | Hardware | Duration | Quality |
| --- | --- | --- | --- |
| Quick Check | Any CPU/GPU | 1–3 minutes | ⭐⭐⭐ |
| Standard Think | Mid-range GPU | 5–15 minutes | ⭐⭐⭐⭐ |
| Deep Reasoning | High-end setup | 30–90 minutes | ⭐⭐⭐⭐⭐ |

### 🎯 Quality vs Speed Trade-offs

```bash
# 🚀 Speed-focused (shallower)
PREDICT=400 CHAINS=6 TIME_BUDGET=180

# ⚖️ Balanced baseline
PREDICT=900 CHAINS=12 TIME_BUDGET=600

# 🎯 Maximum reasoning depth
PREDICT=1600 CHAINS=20 TIME_BUDGET=3600
```

## 🔍 Observability & Debugging

- **`runs/` audit trail:** Raw traces (`*.txt`, `*.json`), vote tallies (`votes.txt`), referee verdicts (`referee.txt`), background logs, and PID markers.
- **Session monitor:** `python3 mjthinking_monitor.py --follow` renders live progress using `session.jsonl` metadata.
- **Quick status:** `python3 mjthinking_status.py` prints a snapshot of the latest session.
- **Metrics rollup:** `python3 mjthinking_metrics.py --limit 20` summarizes success rate, runtime stats, and recent sessions.
- **Control helper:** `python3 mjthinking_ctl.py pause|resume|stop --session <id>` writes commands to `control.ctl`.
- **Adaptive ETA history:** `mjthinking.sh` appends per-round timings to `runs/history_rounds.jsonl`; future sessions blend historical averages into ETA estimates.
- **Round checkpoints:** Each round saves `round_<n>_best.txt` and `round_<n>_snapshot.json` under the session directory for quick rollbacks.
- **History analysis:** `python3 mjthinking_history.py --limit 50` summarizes historical round durations.
- **Connectivity check:** `curl -s ${API:-http://127.0.0.1:11434}/api/tags | jq '.[].name'` (Ollama) or `curl -s ${API:-http://127.0.0.1:1234}/v1/models`
- **Sanity prompt:** `CHAINS=2 PREDICT=200 ./mjthinking_core.sh "Test: what is 2+2?"`
- **Trace search:** `rg "Final Answer:" runs/*.txt`
- **Monitor background runs:** `./monitor7b.sh`

### 🐛 Common Issues

<details>
<summary><strong>🔧 Model Not Found</strong></summary>

```bash
# Ollama (default)
ollama list                         # Inspect installed checkpoints
ollama pull google/gemma-3-12b      # or whichever model tag you need

# OpenAI-compatible servers (LM Studio, vLLM, etc.)
curl -s ${API:-http://127.0.0.1:1234}/v1/models | jq '.data[].id'
```

</details>

<details>
<summary><strong>⏱️ Slow Performance</strong></summary>

```bash
PREDICT=600   # Reduce token budget
BATCH=6       # Fewer concurrent chains
MODEL_FALLBACK=google/gemma-3-27b   # Escalate when problems stay hard
```

</details>

## 🚀 Advanced Usage

### 🎭 Custom Verification

Swap `referee_prompt.txt` for domain-specific validators:

```bash
cp templates/math_referee.txt referee_prompt.txt
cp templates/code_referee.txt referee_prompt.txt
```

### 🔄 Chaining Sessions

```bash
PREV_ANSWER=$(./last_answer7b.sh)
python3 mjthinking_ultra.py "Building on this result: $PREV_ANSWER -- now extend the proof."
```

### 📈 Batch Processing

```bash
while read -r question; do
    echo "Processing: $question"
    ./mjthinking.sh "$question" > "results/$(echo $question | tr ' ' '_').txt"
done < questions.txt
```

## 🛠️ Development & Extension

- **Prompt engineering:** Create specialized templates under `templates/` to enforce proof styles, coding standards, or domain heuristics.
- **Model experiments:** Any Ollama-compatible reasoning model works. Example:

  ```bash
  MODEL=qwen2.5:7b ./mjthinking.sh "Outline GPU memory optimizations."
  MODEL=llama3:8b ./mjthinking.sh "Summarize the Fast Multipole Method."
  ```

- **Metrics logging:** Capture confidence trends by piping controller output to analytics.
- **Resumable sessions:** `./mjthinking.sh --resume <session_id>` loads `manifest.json` + `state.json`, continuing where you left off.
- **Adaptive scheduling:** Automatic confidence tracking adjusts rounds, compares against `TARGET_CONF`, and records trends per round.
- **Validator hooks:** Drop scripts into `validators/` and set `VALIDATOR_HOOKS=math-check,unit-tests` to gate answers beyond the referee.
- **Rich artifacts:** Every session writes `summary.md`, `summary.html`, and `summary.json` alongside per-round snapshots.
- **Queue workflows:** `mjthinking_enqueue.py` + `mjthinking_worker.py` manage background batches; receipts live under `runs/queue_logs/`.
- **Cleanups:** `mjthinking_gc.sh --days=7 --keep=20` trims old sessions when disk space runs low.
- **Plugin hooks:** Drop scripts in `plugins/` to react to lifecycle events (`session_start`, `pre_round`, `post_round`, `session_complete`).
- **REST + UI:** `uvicorn mjthinking_api:app --reload` exposes endpoints; open `web/index.html` against the API for a live dashboard.

### 🧵 Queue Automation

1. Enqueue prompts:

   ```bash
   ./mjthinking_enqueue.py "Analyze the spectral radius of a stochastic matrix"
   ./mjthinking_enqueue.py --file prompts/math_proof.txt --style math
   ```

2. Run the worker (daemon mode):

   ```bash
   ./mjthinking_worker.py --poll-interval 30 --verbose
   ```

3. Inspect receipts/logs in `runs/queue_logs/`.

### 🧹 Session Cleanup

```bash
# Dry-run delete sessions older than 10 days
./mjthinking_gc.sh --days=10 --dry-run

# Keep the latest 25 sessions, delete the rest (with confirmation)
./mjthinking_gc.sh --keep=25
```

### 🌐 REST API & Dashboard

```bash
# Launch API (default: http://127.0.0.1:8000)
uvicorn mjthinking_api:app --reload

# Visit the web dashboard (served as static files)
python3 -m http.server --directory web 3000
# then open http://127.0.0.1:3000 and point it at the API
```

### 🔌 Plugin Hooks

- Create scripts under `plugins/` (bash or python).
- Hooks currently fired: `session_start`, `session_resume`, `pre_round`, `validators_complete`, `post_round`, `session_complete`.
- Example: `plugins/log_round.py` appends summaries to `runs/<id>/plugin_log.jsonl`.

## 📖 FAQ

<details>
<summary><strong>❓ How does MJThinking compare to other reasoning frameworks?</strong></summary>

MJThinking systematically trades time for quality. Instead of single-shot prompts, it layers sampling, planning, and verification to coax small models toward frontier-level answers.

</details>

<details>
<summary><strong>❓ What hardware do I need?</strong></summary>

- Minimum: ~8 GB RAM + CPU (slow but functional)
- Recommended: 16 GB RAM + recent GPU
- Optimal: 32 GB RAM + RTX 4090 (or similar) for long hybrid runs

</details>

<details>
<summary><strong>❓ Can I use cloud-hosted models?</strong></summary>

Yes with adaptation, but the default scripts assume a local Ollama endpoint. Cloud calls can become expensive when hundreds of generations are required per session.

</details>

<details>
<summary><strong>❓ How do I know it worked?</strong></summary>

- Multiple chain transcripts in `runs/*.txt`
- Referee PASS verdicts in `runs/referee.txt`
- Confidence scores exceeding your `CONF` threshold
- Stable final answers across consecutive waves

</details>

## 📄 License

The repository currently has no explicit license. Add one (e.g., MIT, Apache-2.0) before distributing or accepting external contributions.

<div align="center">

🧠 **Give your models time to think deeply.**  
⭐ Star the project • 🐛 Report issues • 💬 Share new reasoning strategies

</div>
