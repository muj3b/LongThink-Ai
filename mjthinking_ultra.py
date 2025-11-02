import os, sys, time, json, re, random, uuid, pathlib, threading, urllib.request, urllib.error

API = os.environ.get("API","http://127.0.0.1:11434")
API_KEY = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
MODEL1 = os.environ.get("MODEL","google/gemma-3-12b")
MODEL2 = os.environ.get("MODEL_FALLBACK","")  # e.g., google/gemma-3-27b
CTX   = int(os.environ.get("CTX","4096"))
TEMP  = float(os.environ.get("TEMP","0.8"))
TOP_P = float(os.environ.get("TOP_P","0.95"))
PREDICT = int(os.environ.get("PREDICT","1400"))
CONF  = float(os.environ.get("CONF","0.66"))             # weighted confidence
BATCH = int(os.environ.get("BATCH","12"))                # chains per wave
MODE  = os.environ.get("MODE","BON")                     # BON|TOT|HYBRID
PLANS = int(os.environ.get("PLANS","3"))                 # ToT: plans per wave
EXPAND= int(os.environ.get("EXPAND","2"))                # ToT: attempts per plan

_time_budget_raw = os.environ.get("TIME_BUDGET","").strip()
AUTO_TIME_BUDGET = _time_budget_raw.lower() in ("", "auto", "adaptive")
_time_budget_fixed = None
if not AUTO_TIME_BUDGET:
    try:
        _time_budget_fixed = max(1, int(float(_time_budget_raw)))
    except ValueError:
        AUTO_TIME_BUDGET = True
TIME_BUDGET_DEFAULT = max(60, int(os.environ.get("TIME_BUDGET_DEFAULT","1800")))
TIME_BUDGET_MIN = max(60, int(os.environ.get("TIME_BUDGET_MIN","300")))
TIME_BUDGET_MAX = max(TIME_BUDGET_MIN, int(os.environ.get("TIME_BUDGET_MAX","7200")))
API_TYPE = os.environ.get("API_TYPE","").lower()
if not API_TYPE:
    if "/v1" in API or API.endswith(":1234"):
        API_TYPE = "openai"
    else:
        API_TYPE = "ollama"

RUNS = pathlib.Path("runs"); RUNS.mkdir(exist_ok=True)
SESSION_ID = os.environ.get("SESSION_ID") or f"ultra_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{uuid.uuid4().hex[:6]}"
SESSION_DIR = RUNS / SESSION_ID; SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_LOG = SESSION_DIR / "session.jsonl"
RESULT_PATH = SESSION_DIR / "result.json"
MANIFEST_PATH = SESSION_DIR / "manifest.json"
PROMPT_TMPL = pathlib.Path("prompt_template.txt").read_text()
REFEREE_TMPL = pathlib.Path("referee_prompt.txt").read_text()
TOT_PLAN_TMPL = pathlib.Path("tot_plan_prompt.txt").read_text()
TOT_ATTEMPT_TMPL = pathlib.Path("tot_attempt_prompt.txt").read_text()
TOT_EVAL_TMPL = pathlib.Path("tot_evaluate_prompt.txt").read_text()
PLAN_BLOCK_RE = re.compile(r'plan\s+(\d+)\s*:\s*(.*?)(?=plan\s+\d+\s*:|$)', re.IGNORECASE | re.S)

PROGRESS_WIDTH = int(os.environ.get("PROGRESS_WIDTH","28"))
_ADAPT_KEYWORDS = [
    "prove", "proof", "theorem", "research", "investigate", "design", "architecture",
    "roadmap", "strategy", "comprehensive", "long-term", "detailed", "analysis",
    "policy", "simulation", "algorithm", "implementation", "evaluate", "comparison",
    "benchmark", "security", "safety", "derivation", "integration", "optimization",
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
    if words > 12:
        complexity += 1
    if words > 28:
        complexity += 1
    if words > 60:
        complexity += 1
    if words > 120:
        complexity += 1
    if any(kw in lower_q for kw in _ADAPT_KEYWORDS):
        complexity += 1
    if "step-by-step" in lower_q or "multi-stage" in lower_q or "deep dive" in lower_q:
        complexity += 1
    budgets = [300, 600, 900, 1200, 1800, 2400, 3600, 5400, 7200]
    idx = min(max(complexity, 0), len(budgets)-1)
    estimated = budgets[idx]
    return max(TIME_BUDGET_MIN, min(TIME_BUDGET_MAX, estimated if AUTO_TIME_BUDGET else max(estimated, TIME_BUDGET_DEFAULT)))


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


def write_manifest(question: str, started_at: float, model: str, time_budget: int):
    manifest = {
        "session_id": SESSION_ID,
        "question": question,
        "start_timestamp": int(started_at),
        "parameters": {
            "MODEL": model,
            "MODEL_FALLBACK": MODEL2,
            "MODE": MODE,
            "TIME_BUDGET": time_budget,
            "CHAINS": BATCH,
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

def post_generate(model, prompt, num_ctx, temperature, top_p, num_predict, seed=None):
    timeout = max(600, num_predict * 2)
    if API_TYPE == "openai":
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": num_predict,
            "n": 1,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{_openai_base()}/completions", data=data, headers={"Content-Type": "application/json"})
        if API_KEY:
            req.add_header("Authorization", f"Bearer {API_KEY}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = (e.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {"response": "", "error": f"HTTP {e.code}: {body}"[:400], "raw": body or None}
        except urllib.error.URLError as e:
            return {"response": "", "error": f"URLError: {e.reason}", "raw": None}
        choice = (raw.get("choices") or [{}])[0]
        text = choice.get("text") or choice.get("message", {}).get("content") or raw.get("output_text", "")
        return {
            "response": text,
            "choices": raw.get("choices"),
            "usage": raw.get("usage"),
            "raw": raw,
        }
    else:
        data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": num_ctx,
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": num_predict,
            },
        }
        if seed is not None:
            data["options"]["seed"] = seed
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(f"{API}/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = (e.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            return {"response": "", "error": f"HTTP {e.code}: {err_body}"[:400], "raw": err_body or None}
        except urllib.error.URLError as e:
            return {"response": "", "error": f"URLError: {e.reason}", "raw": None}

_FINAL_PAT = re.compile(r'final\s*answer\s*:\s*(.*)', re.IGNORECASE)
_BOLD_PAT = re.compile(r'^\*\*([^*]+)\*\*$')
_BOX_PAT = re.compile(r'^\\boxed\{(.*)\}$')
_DOLLAR_PAT = re.compile(r'^\$([^$]*)\$$')


def extract_final_answer(full: str) -> str:
    if not full:
        return ""
    lines = full.splitlines()
    answer = ""
    for idx, ln in enumerate(lines):
        match = _FINAL_PAT.search(ln)
        if not match:
            continue
        candidate = match.group(1).strip()
        if (not candidate) and idx + 1 < len(lines):
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
    p = subprocess.Popen([sys.executable,"canonicalize.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out,_ = p.communicate(ans or "", timeout=20)
    js = json.loads(out)
    return js["text"], js["num"]

def referee(question: str, candidate_text_or_num, model: str, wave_idx: int):
    cand = str(candidate_text_or_num)
    prompt = f"{REFEREE_TMPL}\n\nCandidate Final Answer: {cand}\n\nQuestion:\n{question}\n"
    resp = post_generate(model, prompt, CTX, 0.2, 0.9, min(800, PREDICT))
    text = resp.get("response","")
    path = session_wave_dir(wave_idx) / "referee.txt"
    if text:
        path.write_text(text)
    else:
        path.write_text(resp.get("error",""))
    if resp.get("error"):
        return "UNKNOWN"
    m = re.search(r'(?i)^\s*verdict\s*[:\-]\s*(pass|fail)\s*$', text, re.M)
    return (m.group(1).upper() if m else "UNKNOWN")

def vote_numeric_or_text(finals):
    # finals: list of raw final strings
    pairs=[]
    for s in finals:
        t, n = canonicalize(s)
        pairs.append((t, n, s))
    nums = [x[1] for x in pairs if x[1] is not None]
    if len(nums) >= max(3, len(pairs)//2):
        bucket={}
        for t,n,s in pairs:
            if n is None: continue
            key=f"{n:.10g}"
            bucket.setdefault(key,[]).append(s)
        leader_key, lst = max(bucket.items(), key=lambda kv: len(kv[1]))
        return ("NUM", leader_key, lst, len(lst), len(finals))
    # text fallback
    bucket={}
    for t,n,s in pairs:
        bucket.setdefault(t,[]).append(s)
    leader_key, lst = max(bucket.items(), key=lambda kv: len(kv[1]))
    return ("TXT", leader_key, lst, len(lst), len(finals))

def bon_wave(question, model, wave_idx, n):
    finals=[]
    errors=[]
    lock=threading.Lock()

    def one(i):
        seed=random.randint(0,2**31-1)
        prompt=f"{PROMPT_TMPL}\n\nQuestion:\n{question}\n"
        try:
            resp=post_generate(model, prompt, CTX, TEMP, TOP_P, PREDICT, seed)
        except Exception as exc:
            with lock:
                errors.append(f"generation failed: {exc}")
            return
        txt=resp.get("response","")
        path=session_wave_dir(wave_idx)/f"bon_{i}.txt"
        if txt:
            path.write_text(txt)
        else:
            path.write_text(resp.get("error",""))
        if resp.get("error"):
            with lock:
                errors.append(resp["error"])
            return
        ans=extract_final_answer(txt)
        with lock:
            finals.append(ans)

    threads=[threading.Thread(target=one, args=(i,), daemon=True) for i in range(n)]
    for t in threads: t.start()
    for t in threads: t.join()
    if not finals and errors:
        raise RuntimeError(f"All BON chains failed: {errors[0]}")
    return finals

def tot_wave(question, model, wave_idx, plans, expand):
    # propose plans
    plan_prompt = TOT_PLAN_TMPL.replace("{QUESTION}", question).replace("{NUM_PLANS}", str(plans))
    plan_resp = post_generate(model, plan_prompt, CTX, TEMP, TOP_P, min(800,PREDICT))
    plan_text = plan_resp.get("response","")
    plan_path = session_wave_dir(wave_idx)/"plans.txt"
    if plan_text:
        plan_path.write_text(plan_text)
    else:
        plan_path.write_text(plan_resp.get("error",""))
    if plan_resp.get("error"):
        return []
    # extract plans
    blocks = PLAN_BLOCK_RE.findall(plan_text)
    if not blocks: return []
    plan_map={}
    for num, body in blocks:
        plan_map[int(num)] = body.strip()
    # optional scoring
    joined="\n\n".join([f"PLAN {k}:\n{v}" for k,v in sorted(plan_map.items())])
    eval_prompt = TOT_EVAL_TMPL.replace("{PLANS}", joined).replace("{QUESTION}", question)
    order = sorted(plan_map.keys())
    eval_resp = post_generate(model, eval_prompt, CTX, 0.2, 0.9, 600)
    scores_json = eval_resp.get("response","")
    (session_wave_dir(wave_idx)/"eval.txt").write_text(scores_json or eval_resp.get("error",""))
    if not eval_resp.get("error"):
        try:
            match = re.findall(r'\[[\s\S]*\]', scores_json)[0]
            scores = json.loads(match)
            order = [int(d["plan"]) for d in sorted(scores, key=lambda d: -float(d.get("score",0)))]
        except Exception:
            order = sorted(plan_map.keys())
    # attempt per plan
    finals=[]
    for pid in order:
        plan=plan_map[pid]
        for k in range(expand):
            attempt_prompt = TOT_ATTEMPT_TMPL.replace("{PLAN}", plan).replace("{QUESTION}", question)
            attempt_resp = post_generate(model, attempt_prompt, CTX, TEMP, TOP_P, PREDICT)
            txt = attempt_resp.get("response","")
            path = session_wave_dir(wave_idx)/f"tot_{pid}_{k}.txt"
            if txt:
                path.write_text(txt)
            else:
                path.write_text(attempt_resp.get("error",""))
            if attempt_resp.get("error"):
                continue
            finals.append(extract_final_answer(txt))
    return finals

def run(question):
    global LAST_TIME_BUDGET
    time_budget = _time_budget_fixed if _time_budget_fixed is not None else adaptive_time_budget(question)
    LAST_TIME_BUDGET = time_budget
    start=time.time(); model=MODEL1; weights={}; leader_samples_map={}
    write_manifest(question, start, model, time_budget)
    log_event("session_start", session_id=SESSION_ID, question=question, mode=MODE, model=model, time_budget=time_budget)
    wave=0
    while True:
        elapsed=time.time()-start
        left=time_budget - int(elapsed)
        if left<=0: break
        wave+=1
        if MODE=="BON": finals = bon_wave(question, model, wave, BATCH)
        elif MODE=="TOT": finals = tot_wave(question, model, wave, PLANS, EXPAND)
        else:
            finals = bon_wave(question, model, wave, BATCH) if wave%2==1 else tot_wave(question, model, wave, PLANS, EXPAND)
        if not finals: continue
        keytype, leader_key, leader_samples, c, t = vote_numeric_or_text(finals)
        candidate = leader_key if keytype=="NUM" else leader_samples[0]
        verdict = referee(question, candidate, model, wave)
        gain = c + (0.5 if verdict=="PASS" else 0.0)
        key = (keytype, leader_key, model)
        weights[key] = weights.get(key, 0.0) + gain
        leader_samples_map[key] = leader_samples
        # confidence
        best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
        best_keytype, best_leader_key, best_model = best_key
        tot_w = sum(weights.values())
        conf = best_w / tot_w if tot_w > 0 else 0.0
        progress = render_progress(elapsed, time_budget)
        eta_seconds = max(0, time_budget - int(elapsed)) if time_budget > 0 else -1
        eta_str = format_duration(eta_seconds) if eta_seconds >= 0 else "--"
        elapsed_str = format_duration(int(elapsed))
        print(f"[wave {wave:02d} | {MODE} | model={model}] {progress} elapsed={elapsed_str} eta~{eta_str} vote={c}/{t} verdict={verdict} conf={conf:.2%}")
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
            model=model,
            time_budget=time_budget,
        )
        if conf>=CONF and verdict=="PASS":
            if best_keytype=="NUM":
                final = best_leader_key
            else:
                samples = leader_samples_map.get(best_key, [])
                final = samples[0] if samples else candidate
            log_event("session_complete", session_id=SESSION_ID, status="complete", final_answer=final, confidence=conf, elapsed_seconds=int(elapsed), model=best_model, time_budget=time_budget)
            return final, conf, best_model
        if model==MODEL1 and MODEL2 and wave>=2: model=MODEL2
        if time.time()-start>time_budget: break
    elapsed=time.time()-start
    if not weights:
        log_event("session_complete", session_id=SESSION_ID, status="timeout", final_answer="UNKNOWN", confidence=0.0, elapsed_seconds=int(elapsed), model=model, time_budget=time_budget)
        return "UNKNOWN", 0.0, model
    best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
    best_keytype, best_leader_key, best_model = best_key
    samples = leader_samples_map.get(best_key, [])
    if best_keytype=="NUM":
        final = best_leader_key
    else:
        final = samples[0] if samples else "UNKNOWN"
    conf = best_w/sum(weights.values())
    log_event("session_complete", session_id=SESSION_ID, status="timeout", final_answer=final, confidence=conf, elapsed_seconds=int(elapsed), model=best_model, time_budget=time_budget)
    return final, conf, best_model

if __name__=="__main__":
    if len(sys.argv)<2:
        print("Usage: python3 mjthinking_ultra.py \"YOUR QUESTION\""); sys.exit(1)
    q=sys.argv[1]
    fin, conf, used = run(q)
    RESULT_PATH.write_text(json.dumps({
        "session_id": SESSION_ID,
        "question": q,
        "final_answer": fin,
        "confidence": conf,
        "model": used,
        "time_budget_seconds": LAST_TIME_BUDGET,
        "completed_at": int(time.time()),
    }, indent=2))
    print("\n================== MJThinking ULTRA RESULT ==================")
    print(f"Final Answer: {fin}")
    print(f"Confidence (weighted): {conf:.2%}   Model: {used}")
    print(f"Traces saved in ./runs/{SESSION_ID}")
    print("===========================================================\n")
