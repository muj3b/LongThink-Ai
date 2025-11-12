## Objectives
- Deliver adaptive long-horizon thinking (up to 1–2 hours) with small models, matching or surpassing Kimi K2 Thinking quality.
- Fix input/output reliability, add robust progress and ETA, and stabilize orchestration across CLI/API/Web.
- Integrate modern reasoning strategies (self-consistency, ToT/LATS, reflection, ReAct/tool-use) with dynamic compute allocation.

## Research Highlights
- Kimi K2 Thinking: open-weight reasoning model with tool-use and long-horizon planning; emphasizes inference-time/test-time scaling of thinking and tool calls (Moonshot, Nov 2025) (venturebeat.com, kimi-k2.org, siliconangle.com).
- DeepSeek R1: open-source reasoning and distilled 7B variants; encourages explicit <think> sections and shows strong results on math/coding; suitable small-model baseline (arxiv:2501.12948, HF repo deepseek-ai/DeepSeek-R1).
- Techniques to leverage:
  - Self-Consistency over Chain-of-Thought: sample diverse reasoning paths and vote (arxiv:2203.11171).
  - ReAct for interleaving reasoning and tool calls (arxiv:2210.03629; react-lm.github.io).
  - Tree/Graph-of-Thoughts for multi-path exploration (arxiv:2308.09687; arxiv:2308.08614).
  - LATS (Language Agent Tree Search) for MCTS-based agent search (LangGraph tutorial).

## Current Codebase Assessment (Where to hook in)
- Shell orchestrator: rounds control and event logging `mjthinking.sh:762–1101`; progress bar `mjthinking.sh:61–75`; ETA logic `mjthinking.sh:891–911`.
- Core model calls: OpenAI/Ollama adapters `mjthinking_core.sh:70–109`, final-answer extraction `mjthinking_core.sh:113–171`.
- Python orchestrators: adaptive loops and ETA `mjthinking_ultra.py:371–443`, `mjthinking_ultra7b.py:290–361`; adapters `post_generate`.
- API/Worker/Web: FastAPI endpoints `mjthinking_api.py:249–334`, queue worker `mjthinking_worker.py:139–181`, web `web/index.html:1138–1493`.
- Gaps: fragile prompt templating, coarse progress granularity, unstable ETA when history is sparse, limited streaming, inconsistent error surfacing (esp. `ultra7b.py`).

## Proposed Architecture
- Thinking Orchestrator:
  - Multi-strategy engine combining modes:
    - Self-Consistency majority vote over N CoT samples.
    - ToT/LATS tier for hard tasks (tree search with reflection & verifier scoring).
    - ReAct layer for tool-use (search, calculator, code-runner) with gated invocation.
    - Debate/consensus for tie-breaks; lightweight dual-agent adjudication.
  - Stop criteria: confidence threshold, verifier pass, or budget/time cap.
- Compute Scheduler:
  - Initial difficulty probe to classify task and set budgets (chains, depth, tools).
  - Adaptive scaling: expand or shrink budgets based on early-round signals (conf, variance, verifier scores).
  - Time-aware pacing: budgeted tokens, rounds, and tool steps mapped to wall-clock ETA.
- Verifiers & Rewards:
  - Task-specific checkers (math answer match, code run, factual citations) and process rewards (consistency/entropy penalties).
  - Score aggregator to pick best trajectory and decide continuation.
- Persistence & Observability:
  - Unified session manifest/state and JSONL event stream; wave/round snapshots.
  - Structured progress events (percent, ETA, phase, reasoner mode, tool calls).

## Implementation Plan (Phased)
- Phase 1: Foundations
  - Unify model adapter layer (OpenAI/Ollama/DeepSeek-R1) behind one interface in Python runners; preserve shell path for CLI compatibility.
  - Harden prompt templating with defaults and fallbacks; validate env/config early.
  - Normalized event schema (progress, ETA, mode, verifier scores) and per-iteration streaming logs.
- Phase 2: Adaptive Scheduler & Progress/ETA
  - Difficulty probe and budget planner; dynamic round depth, chains per round, and tool-use gates.
  - ETA: weighted moving average + mode-based estimates; expose ETA confidence.
  - CLI progress: streaming line updates with fine-grained phases; Web UI: event-driven progress with 2–3s refresh and socket fallback.
- Phase 3: Reasoning Strategies
  - Self-Consistency path sampling with majority vote.
  - ToT/LATS: add tree search module; rollouts limited by budget; hook verifier scoring for backprop of scores.
  - ReAct tool-use: searchable web, calculator, code-exec with sandboxed runner; rate limits & caching.
- Phase 4: Verifiers & Stop Criteria
  - Math/string verifiers; code execution with unit-test stubs; factual checks (url evidence + citation scoring).
  - Confidence model: blend of agreement, verifier pass, and uncertainty proxies to stop/escalate.
- Phase 5: UI/API Revamp
  - API: session control (pause/resume), live status, and structured events.
  - Web: real progress bar, ETA, mode badges, tool-call timeline; detailed session page.
  - Terminal monitor: streaming tail with progress/ETA and phase tags.
- Phase 6: Reliability & DX
  - Error surfacing/unification (fix `ultra7b.py` empty errors); retries/backoff tuned per adapter.
  - Config sanity checks; missing dependency detection; graceful degradation.
  - Test suite with simulated prompts; reproducible seeds; benchmark harness.

## Key Changes Mapped to Files
- Orchestrator hooks: `mjthinking.sh:762–1101` (mode transitions, stop criteria), `append_event` `mjthinking.sh:394–399` (structured progress).
- ETA rewrite: `mjthinking.sh:891–911` + history integration `mjthinking.sh:118, 1058–1063`.
- Adapter unification: `mjthinking_ultra.py:142–206`, `mjthinking_ultra7b.py:146–190`, `mjthinking_pro.py:43–106`.
- Web UI progress: `web/index.html:1284–1376` (details render), scheduler `web/index.html:1446–1451`, launch `web/index.html:1461–1493`.
- Error handling fix: `mjthinking_ultra7b.py:167–189` to return structured error.

## Model Integration (Small models, long horizon)
- Prefer DeepSeek-R1-Distill-Qwen-7B for local runs; enforce `<think>` blocks to capture reasoning (HF page, arxiv:2501.12948).
- Ollama/OpenAI-compatible endpoints retained; ensure `API`, `API_TYPE`, `MODEL`, `CTX`, `TEMP`, `TOP_P` sanity checks.

## Progress & ETA Design
- Event schema fields: `phase`, `round`, `chain`, `mode`, `elapsed_ms`, `budget_ms`, `eta_ms`, `eta_conf`, `tokens_generated`, `verifier_scores`.
- CLI: streaming single-line bar with phase segments and ETA; Web: event-driven updates and timeline.
- Estimation sources: initial probe baseline + exponential moving average per phase; history backfill when available.

## Safety & Performance
- Tool-use sandboxing, rate limits, and caching; redact secrets; no logging of keys.
- Bound tree-search breadth/depth for 7B; checkpoint on disk to resume sessions.

## Evaluation & Benchmarks
- Curated tasks: math (AIME-style), coding (HumanEval-lite), factual QA (HotpotQA-lite); measure accuracy, time, and confidence.
- Compare modes: CoT self-consistency vs ToT/LATS vs ReAct; report trade-offs.

## Milestones
- M1: Adapter & event schema; stable progress/ETA.
- M2: Scheduler + self-consistency paths.
- M3: ToT/LATS module with verifiers.
- M4: ReAct tool-use + UI revamp.
- M5: Reliability hardening + test/bench harness.

## References
- Kimi K2 Thinking background and capabilities: venturebeat.com (Moonshot’s Kimi K2 Thinking), kimi-k2.org/blog, siliconangle.com/news.
- DeepSeek R1 release and distilled 7B models: arxiv.org/abs/2501.12948; huggingface.co/deepseek-ai/DeepSeek-R1; github.com/deepseek-ai/DeepSeek-R1; lmstudio.ai/blog/deepseek-r1.
- Self-Consistency CoT: arxiv.org/abs/2203.11171.
- ReAct: arxiv.org/abs/2210.03629; react-lm.github.io.
- Graph-of-Thoughts: arxiv.org/abs/2308.09687; arxiv.org/abs/2305.16582.
- LATS (MCTS search): langchain-ai.github.io/langgraph/tutorials/lats/lats/.