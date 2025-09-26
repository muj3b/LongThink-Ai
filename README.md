# 🧠 MJThinking Reasoning Platform

![Status](https://img.shields.io/badge/status-experimental-blue)
![Language](https://img.shields.io/badge/python-3.11%2B-3776AB)
![API](https://img.shields.io/badge/API-Ollama-green)

<div align="center">

**Transform small, local AI models into deep-reasoning powerhouses.**  
MJThinking lets 7B–14B models think for 30–120+ minutes so they can reach answers that typically demand much larger checkpoints.  
**Quick Start • Architecture • Usage • Configuration**

</div>

> **Quick take:** MJThinking trades *time* for *quality*. Instead of purchasing bigger models, you orchestrate longer, supervised reasoning sessions while keeping everything on local hardware and logging every trace.

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
{{ ... }}

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

### 📋 Prompt Templates

| Template | Controls | Customization |
| --- | --- | --- |
| `prompt_template.txt` | Core reasoning scaffold & final-line contract | 🔧 Essential |
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

3. **Launch your first deep-think session**

   ```bash
   MODEL=deepseek-r1:7b TIME_BUDGET=1800 \
   python3 mjthinking_ultra.py "Prove that the square root of 2 is irrational."
   ```

## 💫 Usage Patterns

### 🎯 Quick Verification (1–2 minutes)

```bash
CHAINS=8 PREDICT=600 ./mjthinking.sh "Explain the quicksort algorithm."
```

### ⚡ Balanced Reasoning (5–10 minutes)

```bash
MODEL=deepseek-r1:7b MODEL_FALLBACK=deepseek-r1:14b \
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
| `MODEL` | `deepseek-r1:7b` | Primary reasoning model | Use your most capable local Ollama checkpoint |
| `MODEL_FALLBACK` | _(empty)_ | Secondary model if consensus stalls | Point to `deepseek-r1:14b` or similar |
| `TIME_BUDGET` | `600` (Pro/Ultra) | Max wall-clock seconds | Increase to unlock deeper reasoning |
| `BATCH` / `CHAINS` | `12` / `10` | Parallel chains per wave/round | Balance throughput vs VRAM and API load |
| `CONF` | `0.66` | Weighted confidence threshold | Raise for stricter consensus |

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
- **Connectivity check:** `curl -s ${API:-http://127.0.0.1:11434}/api/tags | jq '.[].name'`
- **Sanity prompt:** `CHAINS=2 PREDICT=200 ./mjthinking_core.sh "Test: what is 2+2?"`
- **Trace search:** `rg "Final Answer:" runs/*.txt`
- **Monitor background runs:** `./monitor7b.sh`

### 🐛 Common Issues

<details>
<summary><strong>🔧 Model Not Found</strong></summary>

```bash
ollama list          # Inspect installed models
ollama pull deepseek-r1:7b
```

</details>

<details>
<summary><strong>⏱️ Slow Performance</strong></summary>

```bash
PREDICT=600   # Reduce token budget
BATCH=6       # Fewer concurrent chains
MODEL_FALLBACK=deepseek-r1:14b   # Escalate when problems stay hard
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

## 📖 FAQ

<details>
<summary><strong>❓ How does MJThinking compare to other reasoning frameworks?</strong></summary>

MJThinking systematically trades time for quality. Instead of single-shot prompts, it layers sampling, planning, and verification to coax small models toward frontier-level answers.

</details>

<details>
<summary><strong>❓ What hardware do I need?</strong></summary>

- Minimum: ~8 GB RAM + CPU (slow but functional)
- Recommended: 16 GB RAM + recent GPU
- Optimal: 32 GB RAM + RTX 4090 (or similar) for long hybrid runs

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
