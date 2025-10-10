import os, sys, time, json, re, random, pathlib, threading, urllib.request

API = os.environ.get("API","http://127.0.0.1:11434")
MODEL = os.environ.get("MODEL","deepseek-r1:7b")    # 7B ONLY
CTX   = int(os.environ.get("CTX","8192"))           # big scratch ok on 7B
TEMP  = float(os.environ.get("TEMP","0.8"))
TOP_P = float(os.environ.get("TOP_P","0.95"))
PREDICT = int(os.environ.get("PREDICT","1600"))     # long chains
TIME_BUDGET = int(os.environ.get("TIME_BUDGET","1800"))  # seconds
CONF  = float(os.environ.get("CONF","0.66"))        # weighted confidence target
BATCH = int(os.environ.get("BATCH","12"))           # chains per wave
MODE  = os.environ.get("MODE","HYBRID")             # BON|TOT|HYBRID
PLANS = int(os.environ.get("PLANS","3"))            # ToT: plans per wave
EXPAND= int(os.environ.get("EXPAND","2"))           # ToT: attempts per plan

BASE_DIR = pathlib.Path(__file__).resolve().parent
RUNS = BASE_DIR / "runs"; RUNS.mkdir(exist_ok=True)
PROMPT_TMPL = (BASE_DIR/"prompt_template.txt").read_text()
REFEREE_TMPL = (BASE_DIR/"referee_prompt.txt").read_text()
TOT_PLAN_TMPL = (BASE_DIR/"tot_plan_prompt.txt").read_text()
TOT_ATTEMPT_TMPL = (BASE_DIR/"tot_attempt_prompt.txt").read_text()
TOT_EVAL_TMPL = (BASE_DIR/"tot_evaluate_prompt.txt").read_text()

def post_generate(prompt, num_predict, temperature=None, seed=None):
    opts = {"num_ctx": CTX, "top_p": TOP_P, "num_predict": num_predict}
    if temperature is None: temperature = TEMP
    opts["temperature"] = temperature
    if seed is not None: opts["seed"] = seed
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "options": opts}).encode("utf-8")
    req  = urllib.request.Request(f"{API}/api/generate", data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=max(600, num_predict*2)) as r:
        return json.loads(r.read().decode("utf-8")).get("response","")

def extract_final_answer(full: str) -> str:
    lines = (full or "").splitlines()
    for i, ln in enumerate(lines):
        m = re.search(r'final\s*answer\s*:\s*', ln, flags=re.IGNORECASE)
        if m:
            val = ln[m.end():]
            if re.fullmatch(r'[*`_\s-]*', (val or '')) and i+1 < len(lines):
                val = lines[i+1]
            return re.sub(r'[*`_]', '', (val or '')).strip()
    return ""

def canonicalize(ans: str):
    import subprocess
    p = subprocess.Popen([sys.executable, str(BASE_DIR/"canonicalize.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out,_ = p.communicate(ans or "", timeout=20)
    js = json.loads(out or "{}")
    return js.get("text", (ans or "").strip().lower()), js.get("num")

def referee(question: str, candidate: str, session_dir: pathlib.Path):
    prompt = f"{REFEREE_TMPL}\n\nCandidate Final Answer: {candidate}\n\nQuestion:\n{question}\n"
    text = post_generate(prompt, num_predict=min(800,PREDICT), temperature=0.2)
    (session_dir/"referee.txt").write_text(text)
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

def bon_wave(question, wave_idx, n, session_dir: pathlib.Path):
    finals=[]; threads=[]
    def one(i):
        seed = random.randint(0,2**31-1)
        prompt = f"{PROMPT_TMPL}\n\nQuestion:\n{question}\n"
        txt = post_generate(prompt, num_predict=PREDICT, seed=seed)
        (session_dir/f"wave_{wave_idx}_bon_chain_{i}.txt").write_text(txt)
        finals.append(extract_final_answer(txt))
    for i in range(n):
        t=threading.Thread(target=one,args=(i,)); t.daemon=True; t.start(); threads.append(t)
    for t in threads: t.join()
    return finals

def tot_wave(question, wave_idx, plans, expand, session_dir: pathlib.Path):
    plan_prompt = TOT_PLAN_TMPL.replace("{QUESTION}", question).replace("N", str(plans))
    plan_text = post_generate(plan_prompt, num_predict=min(800,PREDICT))
    (session_dir/f"wave_{wave_idx}_plans.txt").write_text(plan_text)
    blocks = re.findall(r'(?i)plan\s+(\d+)\s*:\s*(.*?)(?=(?i)plan\s+\d+\s*:|$)', plan_text, re.S)
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
            (session_dir/f"wave_{wave_idx}_tot_plan_{pid}_attempt_{k}.txt").write_text(txt)
            finals.append(extract_final_answer(txt))
    return finals

def run(question):
    start=time.time()
    session_id = f"ultra7b_{time.strftime('%Y%m%d_%H%M%S')}"
    session_dir = RUNS / session_id
    session_dir.mkdir(exist_ok=True)
    print(f"[*] Starting session: {session_id}. Traces will be saved in {session_dir}")

    weights={}
    wave=0
    while True:
        left = TIME_BUDGET - int(time.time()-start)
        if left<=0: break
        wave+=1

        current_mode = MODE.upper()
        if current_mode == "HYBRID":
            current_mode = "BON" if wave % 2 == 1 else "TOT"

        if current_mode=="BON":
            finals = bon_wave(question, wave, BATCH, session_dir)
        elif current_mode=="TOT":
            finals = tot_wave(question, wave, PLANS, EXPAND, session_dir)
        else:
            print(f"[!] Invalid mode '{MODE}' in wave {wave}. Defaulting to BON.", file=sys.stderr)
            finals = bon_wave(question, wave, BATCH, session_dir)

        if not finals: continue
        keytype, leader_key, leader_samples, c, t = vote_numeric_or_text(finals)
        candidate = leader_key if keytype=="NUM" else leader_samples[0]
        verdict = referee(question, candidate, session_dir)
        gain = c + (0.5 if verdict=="PASS" else 0.0)
        weights[(keytype, leader_key)] = weights.get((keytype, leader_key), 0.0) + gain
        best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
        tot_w = sum(weights.values()); conf = best_w / tot_w if tot_w>0 else 0.0
        print(f"[wave {wave:02d} | {current_mode} | model={MODEL}] vote={c}/{t} verdict={verdict} conf={conf:.2%} left={left}s")
        if conf>=CONF and verdict=="PASS":
            return (candidate), conf

    if not weights: return "UNKNOWN", 0.0
    best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
    final_key_type, final_key_val = best_key
    return final_key_val, best_w/sum(weights.values())

if __name__=="__main__":
    if len(sys.argv)<2:
        print('Usage: TIME_BUDGET=1800 BATCH=12 PREDICT=1600 CTX=8192 MODE=HYBRID python3 mjthinking_ultra7b.py "YOUR QUESTION"')
        sys.exit(1)
    q = sys.argv[1]
    fin, conf = run(q)
    print("\n================== MJThinking ULTRA — 7B ONLY ==================")
    print(f"Final Answer: {fin}")
    print(f"Confidence (weighted): {conf:.2%}   Model: {MODEL}")
    print("See session directory logged at startup for traces.")
    print("===============================================================\n")
