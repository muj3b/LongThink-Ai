import os, sys, time, json, re, random, uuid, pathlib, threading, urllib.request, urllib.error

API = os.environ.get("API","http://127.0.0.1:11434")
API_KEY = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("MODEL","google/gemma-3-12b")    # default Gemma 3 12B
CTX   = int(os.environ.get("CTX","8192"))           # big scratch ok on 7B
TEMP  = float(os.environ.get("TEMP","0.8"))
TOP_P = float(os.environ.get("TOP_P","0.95"))
PREDICT = int(os.environ.get("PREDICT","1600"))     # long chains
CONF  = float(os.environ.get("CONF","0.66"))        # weighted confidence target
BATCH = int(os.environ.get("BATCH","12"))           # chains per wave
MODE  = os.environ.get("MODE","HYBRID")             # BON|TOT|HYBRID
PLANS = int(os.environ.get("PLANS","3"))            # ToT: plans per wave
EXPAND= int(os.environ.get("EXPAND","2"))           # ToT: attempts per plan

API_TYPE = os.environ.get("API_TYPE","").lower()
if not API_TYPE:
    if "/v1" in API or API.endswith(":1234"):
        API_TYPE = "openai"
    else:
        API_TYPE = "ollama"

_time_budget_raw = os.environ.get("TIME_BUDGET","").strip()
AUTO_TIME_BUDGET = _time_budget_raw.lower() in ("", "auto", "adaptive")
_time_budget_fixed = None
if not AUTO_TIME_BUDGET:
    try:
        _time_budget_fixed = max(1, int(float(_time_budget_raw)))
    except ValueError:
        AUTO_TIME_BUDGET = True
TIME_BUDGET_DEFAULT = max(600, int(os.environ.get("TIME_BUDGET_DEFAULT","3600")))
TIME_BUDGET_MIN = max(120, int(os.environ.get("TIME_BUDGET_MIN","600")))
TIME_BUDGET_MAX = max(TIME_BUDGET_MIN, int(os.environ.get("TIME_BUDGET_MAX","10800")))

BASE_DIR = pathlib.Path(__file__).resolve().parent
RUNS = BASE_DIR / "runs"; RUNS.mkdir(exist_ok=True)
SESSION_ID = os.environ.get("SESSION_ID") or f"ultra7b_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{uuid.uuid4().hex[:6]}"
SESSION_DIR = RUNS / SESSION_ID; SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_LOG = SESSION_DIR / "session.jsonl"
RESULT_PATH = SESSION_DIR / "result.json"
MANIFEST_PATH = SESSION_DIR / "manifest.json"
PROMPT_TMPL = (BASE_DIR/"prompt_template.txt").read_text()
REFEREE_TMPL = (BASE_DIR/"referee_prompt.txt").read_text()
TOT_PLAN_TMPL = (BASE_DIR/"tot_plan_prompt.txt").read_text()
TOT_ATTEMPT_TMPL = (BASE_DIR/"tot_attempt_prompt.txt").read_text()
TOT_EVAL_TMPL = (BASE_DIR/"tot_evaluate_prompt.txt").read_text()
PLAN_BLOCK_RE = re.compile(r'plan\s+(\d+)\s*:\s*(.*?)(?=plan\s+\d+\s*:|$)', re.IGNORECASE | re.S)
_FINAL_PAT = re.compile(r'final\s*answer\s*:\s*(.*)', re.IGNORECASE)
_BOLD_PAT = re.compile(r'^\*\*([^*]+)\*\*$')
_BOX_PAT = re.compile(r'^\\boxed\{(.*)\}$')
_DOLLAR_PAT = re.compile(r'^\$([^$]*)\$$')
PROGRESS_WIDTH = int(os.environ.get("PROGRESS_WIDTH","28"))
_ADAPT_KEYWORDS = [
    "prove", "proof", "theorem", "research", "investigate", "design", "architecture",
    "roadmap", "strategy", "comprehensive", "long-term", "detailed", "analysis",
    "policy", "simulation", "algorithm", "implementation", "evaluate", "comparison",
    "benchmark", "security", "safety", "derivation", "integration", "optimization",
    "whitepaper", "thesis", "deep dive", "roadmap", "multi-step",
]
LAST_TIME_BUDGET = None


def session_wave_dir(wave_idx: int) -> pathlib.Path:
    path = SESSION_DIR / f"wave_{wave_idx:02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def adaptive_time_budget(question: str) -> int:
    words = len(re.findall(r"\w+", question or ""))
    lower_q = (question or "").lower()
    complexity = 0
    if words > 16:
        complexity += 1
    if words > 40:
        complexity += 1
    if words > 90:
        complexity += 1
    if words > 160:
        complexity += 1
    if any(kw in lower_q for kw in _ADAPT_KEYWORDS):
        complexity += 1
    if "step-by-step" in lower_q or "multi-stage" in lower_q or "comprehensive" in lower_q:
        complexity += 1
    budgets = [900, 1500, 2100, 3000, 4200, 5400, 7200, 9000, 10800]
    idx = min(max(complexity, 0), len(budgets)-1)
    estimated = budgets[idx]
    target = max(estimated, TIME_BUDGET_DEFAULT) if not AUTO_TIME_BUDGET else estimated
    return max(TIME_BUDGET_MIN, min(TIME_BUDGET_MAX, target))

def format_duration(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    mins, sec = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h{mins:02d}m{sec:02d}s"
    if mins:
        return f"{mins}m{sec:02d}s"
    return f"{sec}s"


def render_progress(elapsed: float, budget: int) -> str:
    if budget <= 0:
        return "[progress unavailable]"
    ratio = max(0.0, min(1.0, elapsed / budget))
    filled = min(PROGRESS_WIDTH, int(round(ratio * PROGRESS_WIDTH)))
    empty = PROGRESS_WIDTH - filled
    bar = f"[{'#' * filled}{'-' * empty}]"
    return f"{bar} {ratio*100:5.1f}%"


def log_event(event: str, **fields):
    payload = {"event": event, **fields}
    payload.setdefault("timestamp", int(time.time()))
    with SESSION_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def write_manifest(question: str, started_at: float, time_budget: int):
    manifest = {
        "session_id": SESSION_ID,
        "question": question,
        "start_timestamp": int(started_at),
        "parameters": {
            "MODEL": MODEL,
            "MODE": MODE,
            "TIME_BUDGET": time_budget,
            "BATCH": BATCH,
            "PLANS": PLANS,
            "EXPAND": EXPAND,
            "CONF": CONF,
            "PREDICT": PREDICT,
            "CTX": CTX,
            "TEMP": TEMP,
            "TOP_P": TOP_P,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

def _openai_base() -> str:
    base = API.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base

def post_generate(prompt, num_predict, temperature=None, seed=None):
    if temperature is None:
        temperature = TEMP
    timeout = max(600, num_predict * 2)
    if API_TYPE == "openai":
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": TOP_P,
            "max_tokens": num_predict,
            "n": 1,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{_openai_base()}/completions", data=data, headers={"Content-Type":"application/json"})
        if API_KEY:
            req.add_header("Authorization", f"Bearer {API_KEY}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                msg = (e.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                msg = ""
            return ""
        except urllib.error.URLError:
            return ""
        choice = (raw.get("choices") or [{}])[0]
        return choice.get("text") or choice.get("message", {}).get("content") or raw.get("output_text", "")
    else:
        opts = {"num_ctx": CTX, "top_p": TOP_P, "num_predict": num_predict, "temperature": temperature}
        if seed is not None:
            opts["seed"] = seed
        body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "options": opts}).encode("utf-8")
        req = urllib.request.Request(f"{API}/api/generate", data=body, headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")).get("response","")
        except urllib.error.HTTPError:
            return ""
        except urllib.error.URLError:
            return ""

def extract_final_answer(full: str) -> str:
    if not full:
        return ""
    lines = full.splitlines()
    answer = ""
    for idx, ln in enumerate(lines):
        m = _FINAL_PAT.search(ln)
        if not m:
            continue
        candidate = m.group(1).strip()
        if not candidate and idx + 1 < len(lines):
            candidate = lines[idx + 1].strip()
        answer = candidate.strip()
    if not answer:
        return ""
    bold = _BOLD_PAT.fullmatch(answer)
    if bold:
        answer = bold.group(1)
    boxed = _BOX_PAT.fullmatch(answer)
    if boxed:
        answer = boxed.group(1)
    dollar = _DOLLAR_PAT.fullmatch(answer)
    if dollar:
        answer = dollar.group(1)
    answer = answer.strip()
    if all(ch in "*`_- " for ch in answer):
        return ""
    return answer

def canonicalize(ans: str):
    import subprocess
    p = subprocess.Popen([sys.executable, str(BASE_DIR/"canonicalize.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out,_ = p.communicate(ans or "", timeout=20)
    js = json.loads(out or "{}")
    return js.get("text", (ans or "").strip().lower()), js.get("num")

def referee(question: str, candidate: str, wave_idx: int):
    prompt = f"{REFEREE_TMPL}\n\nCandidate Final Answer: {candidate}\n\nQuestion:\n{question}\n"
    text = post_generate(prompt, num_predict=min(800,PREDICT), temperature=0.2)
    (session_wave_dir(wave_idx)/"referee.txt").write_text(text)
    m = re.search(r'(?i)^\s*verdict\s*[:\-]\s*(pass|fail)\s*$', text, re.M)
    return (m.group(1).upper() if m else "UNKNOWN")

def vote_numeric_or_text(finals):
    pairs=[]
    for s in finals:
        t,n = canonicalize(s); pairs.append((t,n,s))
    nums = [x[1] for x in pairs if x[1] is not None]
    if len(nums) >= max(3, len(pairs)//2):
        bucket={}
        for t,n,s in pairs:
            if n is None: continue
            key=f"{n:.10g}"; bucket.setdefault(key,[]).append(s)
        leader_key, lst = max(bucket.items(), key=lambda kv: len(kv[1]))
        return ("NUM", leader_key, lst, len(lst), len(finals))
    bucket={}
    for t,n,s in pairs:
        bucket.setdefault(t,[]).append(s)
    leader_key, lst = max(bucket.items(), key=lambda kv: len(kv[1]))
    return ("TXT", leader_key, lst, len(lst), len(finals))

def bon_wave(question, wave_idx, n):
    finals=[]; threads=[]
    def one(i):
        seed = random.randint(0,2**31-1)
        prompt = f"{PROMPT_TMPL}\n\nQuestion:\n{question}\n"
        txt = post_generate(prompt, num_predict=PREDICT, seed=seed)
        (session_wave_dir(wave_idx)/f"bon_{i}.txt").write_text(txt)
        finals.append(extract_final_answer(txt))
    for i in range(n):
        t=threading.Thread(target=one,args=(i,)); t.daemon=True; t.start(); threads.append(t)
    for t in threads: t.join()
    return finals

def tot_wave(question, wave_idx, plans, expand):
    plan_prompt = TOT_PLAN_TMPL.replace("{QUESTION}", question).replace("{NUM_PLANS}", str(plans))
    plan_text = post_generate(plan_prompt, num_predict=min(800,PREDICT))
    (session_wave_dir(wave_idx)/"plans.txt").write_text(plan_text)
    blocks = PLAN_BLOCK_RE.findall(plan_text)
    if not blocks: return []
    plan_map = {int(num): body.strip() for num,body in blocks}
    joined = "\n\n".join([f"PLAN {k}:\n{v}" for k,v in sorted(plan_map.items())])
    eval_prompt = TOT_EVAL_TMPL.replace("{PLANS}", joined).replace("{QUESTION}", question)
    try:
        jtxt = post_generate(eval_prompt, num_predict=600, temperature=0.2)
        scores = json.loads(re.findall(r'\[[\s\S]*\]', jtxt)[0])
        order = [int(d["plan"]) for d in sorted(scores, key=lambda d: -float(d.get("score",0)))]
    except Exception:
        order = sorted(plan_map.keys())
    finals=[]
    for pid in order:
        plan = plan_map[pid]
        for k in range(expand):
            attempt_prompt = TOT_ATTEMPT_TMPL.replace("{PLAN}", plan).replace("{QUESTION}", question)
            txt = post_generate(attempt_prompt, num_predict=PREDICT)
            (session_wave_dir(wave_idx)/f"tot_{pid}_{k}.txt").write_text(txt)
            finals.append(extract_final_answer(txt))
    return finals

def run(question):
    global LAST_TIME_BUDGET
    time_budget = _time_budget_fixed if _time_budget_fixed is not None else adaptive_time_budget(question)
    LAST_TIME_BUDGET = time_budget
    start=time.time()
    write_manifest(question, start, time_budget)
    log_event("session_start", session_id=SESSION_ID, question=question, mode=MODE, model=MODEL, time_budget=time_budget)
    weights={}
    leader_samples_map={}
    wave=0
    while True:
        elapsed=time.time()-start
        left = time_budget - int(elapsed)
        if left<=0: break
        wave+=1
        if MODE=="BON":
            finals = bon_wave(question, wave, BATCH)
        elif MODE=="TOT":
            finals = tot_wave(question, wave, PLANS, EXPAND)
        else:
            finals = bon_wave(question, wave, BATCH) if wave%2==1 else tot_wave(question, wave, PLANS, EXPAND)
        if not finals:
            continue
        keytype, leader_key, leader_samples, c, t = vote_numeric_or_text(finals)
        candidate = leader_key if keytype=="NUM" else leader_samples[0]
        verdict = referee(question, candidate, wave)
        gain = c + (0.5 if verdict=="PASS" else 0.0)
        key = (keytype, leader_key)
        weights[key] = weights.get(key, 0.0) + gain
        leader_samples_map[key] = leader_samples
        best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
        tot_w = sum(weights.values()); conf = best_w / tot_w if tot_w>0 else 0.0
        progress = render_progress(elapsed, time_budget)
        eta_seconds = max(0, time_budget - int(elapsed)) if time_budget > 0 else -1
        eta_str = format_duration(eta_seconds) if eta_seconds >= 0 else "--"
        elapsed_str = format_duration(int(elapsed))
        print(f"[wave {wave:02d} | {MODE} | model={MODEL}] {progress} elapsed={elapsed_str} eta~{eta_str} vote={c}/{t} verdict={verdict} conf={conf:.2%}")
        log_event(
            "round_complete",
            session_id=SESSION_ID,
            round=wave,
            majority_count=c,
            majority_total=t,
            referee_verdict=verdict,
            numeric_verdict=keytype,
            elapsed_seconds=int(elapsed),
            eta_seconds=(eta_seconds if eta_seconds >= 0 else None),
            confidence=conf,
            model=MODEL,
            time_budget=time_budget,
        )
        if conf>=CONF and verdict=="PASS":
            if best_key[0]=="NUM":
                final = best_key[1]
            else:
                samples = leader_samples_map.get(best_key, [])
                final = samples[0] if samples else candidate
            log_event("session_complete", session_id=SESSION_ID, status="complete", final_answer=final, confidence=conf, elapsed_seconds=int(elapsed), model=MODEL, time_budget=time_budget)
            return final, conf
    elapsed=time.time()-start
    if not weights:
        log_event("session_complete", session_id=SESSION_ID, status="timeout", final_answer="UNKNOWN", confidence=0.0, elapsed_seconds=int(elapsed), model=MODEL, time_budget=time_budget)
        return "UNKNOWN", 0.0
    best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
    if best_key[0]=="NUM":
        final = best_key[1]
    else:
        samples = leader_samples_map.get(best_key, [])
        final = samples[0] if samples else "UNKNOWN"
    conf = best_w/sum(weights.values())
    log_event("session_complete", session_id=SESSION_ID, status="timeout", final_answer=final, confidence=conf, elapsed_seconds=int(elapsed), model=MODEL, time_budget=time_budget)
    return final, conf

if __name__=="__main__":
    if len(sys.argv)<2:
        print('Usage: TIME_BUDGET=auto BATCH=12 PREDICT=1600 CTX=8192 MODE=HYBRID python3 mjthinking_ultra7b.py "YOUR QUESTION"')
        sys.exit(1)
    q = sys.argv[1]
    fin, conf = run(q)
    RESULT_PATH.write_text(json.dumps({
        "session_id": SESSION_ID,
        "question": q,
        "final_answer": fin,
        "confidence": conf,
        "model": MODEL,
        "time_budget_seconds": LAST_TIME_BUDGET,
        "completed_at": int(time.time()),
    }, indent=2))
    print("\n================== MJThinking ULTRA — 7B ONLY ==================")
    print(f"Final Answer: {fin}")
    print(f"Confidence (weighted): {conf:.2%}   Model: {MODEL}")
    print(f"Traces saved in ./runs/{SESSION_ID}")
    print("===============================================================\n")
