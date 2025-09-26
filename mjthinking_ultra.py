import os, sys, time, json, math, re, random, pathlib, threading, urllib.request, urllib.error

API = os.environ.get("API","http://127.0.0.1:11434")
MODEL1 = os.environ.get("MODEL","deepseek-r1:7b")
MODEL2 = os.environ.get("MODEL_FALLBACK","")  # e.g., deepseek-r1:14b
CTX   = int(os.environ.get("CTX","4096"))
TEMP  = float(os.environ.get("TEMP","0.8"))
TOP_P = float(os.environ.get("TOP_P","0.95"))
PREDICT = int(os.environ.get("PREDICT","1400"))
TIME_BUDGET = int(os.environ.get("TIME_BUDGET","600"))  # seconds
CONF  = float(os.environ.get("CONF","0.66"))             # weighted confidence
BATCH = int(os.environ.get("BATCH","12"))                # chains per wave
MODE  = os.environ.get("MODE","BON")                     # BON|TOT|HYBRID
PLANS = int(os.environ.get("PLANS","3"))                 # ToT: plans per wave
EXPAND= int(os.environ.get("EXPAND","2"))                # ToT: attempts per plan

RUNS = pathlib.Path("runs"); RUNS.mkdir(exist_ok=True)
PROMPT_TMPL = pathlib.Path("prompt_template.txt").read_text()
REFEREE_TMPL = pathlib.Path("referee_prompt.txt").read_text()
TOT_PLAN_TMPL = pathlib.Path("tot_plan_prompt.txt").read_text()
TOT_ATTEMPT_TMPL = pathlib.Path("tot_attempt_prompt.txt").read_text()
TOT_EVAL_TMPL = pathlib.Path("tot_evaluate_prompt.txt").read_text()

def post_generate(model, prompt, num_ctx, temperature, top_p, num_predict, seed=None):
    data = {"model": model, "prompt": prompt, "stream": False,
            "options": {"num_ctx": num_ctx, "temperature": temperature, "top_p": top_p, "num_predict": num_predict}}
    if seed is not None: data["options"]["seed"] = seed
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(f"{API}/api/generate", data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=max(600, num_predict*2)) as r:
        return json.loads(r.read().decode("utf-8"))

def extract_final_answer(full: str) -> str:
    lines = (full or "").splitlines()
    for i, ln in enumerate(lines):
        if re.search(r'(?i)final\s*answer\s*:', ln):
            val = re.sub(r'.*?(?i)final\s*answer\s*:\s*', '', ln)
            if re.fullmatch(r'[*`_\s-]*', val or '') and i+1 < len(lines):
                val = lines[i+1]
            return re.sub(r'[*`_]', '', val or '').strip()
    return ""

def canonicalize(ans: str):
    import subprocess
    p = subprocess.Popen([sys.executable,"canonicalize.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out,_ = p.communicate(ans or "", timeout=20)
    js = json.loads(out)
    return js["text"], js["num"]

def referee(question: str, candidate_text_or_num, model: str):
    cand = str(candidate_text_or_num)
    prompt = f"{REFEREE_TMPL}\n\nCandidate Final Answer: {cand}\n\nQuestion:\n{question}\n"
    resp = post_generate(model, prompt, CTX, 0.2, 0.9, min(800, PREDICT))
    text = resp.get("response","")
    pathlib.Path("runs/referee.txt").write_text(text)
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
    threads=[]
    lock=threading.Lock()
    def one(i):
        seed=random.randint(0,2**31-1)
        prompt=f"{PROMPT_TMPL}\n\nQuestion:\n{question}\n"
        try:
            resp=post_generate(model, prompt, CTX, TEMP, TOP_P, PREDICT, seed)
            txt=resp.get("response",""); (RUNS/f"{wave}_bon_{i}.txt").write_text(txt)
            finals.append(extract_final_answer(txt))
        except Exception as e:
            finals.append("")
    for i in range(n):
        t=threading.Thread(target=one,args=(i,)); t.daemon=True; t.start(); threads.append(t)
    for t in threads: t.join()
    return finals

def tot_wave(question, model, wave_idx, plans, expand):
    # propose plans
    plan_prompt = TOT_PLAN_TMPL.replace("{QUESTION}", question).replace("N", str(plans))
    plan_text = post_generate(model, plan_prompt, CTX, TEMP, TOP_P, min(800,PREDICT)).get("response","")
    (RUNS/f"{wave_idx}_plans.txt").write_text(plan_text)
    # extract plans
    blocks = re.findall(r'(?i)plan\s+(\d+)\s*:\s*(.*?)(?=(?i)plan\s+\d+\s*:|$)', plan_text, re.S)
    if not blocks: return []
    plan_map={}
    for num, body in blocks:
        plan_map[int(num)] = body.strip()
    # optional scoring
    joined="\n\n".join([f"PLAN {k}:\n{v}" for k,v in sorted(plan_map.items())])
    eval_prompt = TOT_EVAL_TMPL.replace("{PLANS}", joined).replace("{QUESTION}", question)
    try:
        scores_json = post_generate(model, eval_prompt, CTX, 0.2, 0.9, 600).get("response","[]")
        scores = json.loads(re.findall(r'\[[\s\S]*\]', scores_json)[0])
        order = [int(d["plan"]) for d in sorted(scores, key=lambda d: -float(d.get("score",0)))]
    except Exception:
        order = sorted(plan_map.keys())
    # attempt per plan
    finals=[]
    for pid in order:
        plan=plan_map[pid]
        for k in range(expand):
            attempt_prompt = TOT_ATTEMPT_TMPL.replace("{PLAN}", plan).replace("{QUESTION}", question)
            txt = post_generate(model, attempt_prompt, CTX, TEMP, TOP_P, PREDICT).get("response","")
            (RUNS/f"{wave_idx}_tot_{pid}_{k}.txt").write_text(txt)
            finals.append(extract_final_answer(txt))
    return finals

def run(question):
    start=time.time(); model=MODEL1; weights={}
    while True:
        left=TIME_BUDGET - int(time.time()-start)
        if left<=0: break
        wave=len(list(RUNS.glob("*_bon_*"))) + len(list(RUNS.glob("*_tot_*"))) + 1
        if MODE=="BON": finals = bon_wave(question, model, wave, BATCH)
        elif MODE=="TOT": finals = tot_wave(question, model, wave, PLANS, EXPAND)
        else:
            finals = bon_wave(question, model, wave, BATCH) if wave%2==1 else tot_wave(question, model, wave, PLANS, EXPAND)
        if not finals: continue
        keytype, leader_key, leader_samples, c, t = vote_numeric_or_text(finals)
        candidate = leader_key if keytype=="NUM" else leader_samples[0]
        verdict = referee(question, candidate, model)
        gain = c + (0.5 if verdict=="PASS" else 0.0)
        weights[(keytype,leader_key,model)] = weights.get((keytype,leader_key,model),0.0) + gain
        # confidence
        best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
        tot_w = sum(weights.values())
        conf = best_w/ tot_w if tot_w>0 else 0.0
        print(f"[wave {wave:02d} | {MODE} | model={model}] vote={c}/{t} verdict={verdict} conf={conf:.2%} left={left}s")
        if conf>=CONF and verdict=="PASS":
            final = best_key[0][1] if best_key[0][0]=="NUM" else candidate
            return final, conf, model
        if model==MODEL1 and MODEL2 and wave>=2: model=MODEL2
        if time.time()-start>TIME_BUDGET: break
    if not weights: return "UNKNOWN", 0.0, model
    best_key, best_w = max(weights.items(), key=lambda kv: kv[1])
    final = best_key[0][1] if best_key[0][0]=="NUM" else "UNKNOWN"
    return final, best_w/sum(weights.values()), best_key[0][2]

if __name__=="__main__":
    if len(sys.argv)<2:
        print("Usage: python3 mjthinking_ultra.py \"YOUR QUESTION\""); sys.exit(1)
    q=sys.argv[1]
    fin, conf, used = run(q)
    print("\n================== MJThinking ULTRA RESULT ==================")
    print(f"Final Answer: {fin}")
    print(f"Confidence (weighted): {conf:.2%}   Model: {used}")
    print("Traces saved in ./runs/")
    print("===========================================================\n")
