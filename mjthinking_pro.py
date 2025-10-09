import os, sys, time, json, math, re, threading, queue, urllib.request, urllib.error, ssl, random, pathlib, collections

API = os.environ.get("API", "http://127.0.0.1:11434")
API_KEY = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
MODEL1 = os.environ.get("MODEL", "google/gemma-3-12b")
MODEL2 = os.environ.get("MODEL_FALLBACK", "")  # e.g., "google/gemma-3-27b" (optional)
CTX   = int(os.environ.get("CTX", "8192"))
TEMP  = float(os.environ.get("TEMP", "0.8"))
TOP_P = float(os.environ.get("TOP_P", "0.95"))
PREDICT = int(os.environ.get("PREDICT", "1400"))
BATCH  = int(os.environ.get("BATCH", "12"))        # chains per wave
CONF   = float(os.environ.get("CONF", "0.66"))      # min weighted confidence to stop
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", "600"))  # seconds
REF_TEMP = float(os.environ.get("REF_TEMP", "0.2"))
BASE_DIR = pathlib.Path(__file__).resolve().parent
RUNS = BASE_DIR / "runs"; RUNS.mkdir(exist_ok=True)
API_TYPE = os.environ.get("API_TYPE", "").lower()
if not API_TYPE:
    if "/v1" in API or API.endswith(":1234"):
        API_TYPE = "openai"
    else:
        API_TYPE = "ollama"


def read_file(p):
    return (BASE_DIR / p).read_text()


PROMPT_TMPL = read_file("prompt_template.txt")
REFEREE_TMPL = read_file("referee_prompt.txt")
_FINAL_PAT = re.compile(r'final\s*answer\s*:\s*(.*)', re.IGNORECASE)
_BOLD_PAT = re.compile(r'^\*\*([^*]+)\*\*$')
_BOX_PAT = re.compile(r'^\\boxed\{(.*)\}$')
_DOLLAR_PAT = re.compile(r'^\$([^$]*)\$$')

def _openai_base() -> str:
    base = API.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def post_generate(model, prompt, num_ctx, temperature, top_p, num_predict, seed=None):
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
            with urllib.request.urlopen(req, timeout=600) as r:
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
                "num_predict": num_predict
            }
        }
        if seed is not None:
            data["options"]["seed"] = seed
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(f"{API}/api/generate", data=body, headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
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


def extract_final_answer(text: str) -> str:
    # Find "Final Answer:" line; if empty/markdown, use next non-empty line.
    lines = text.splitlines()
    answer = ""
    for idx, ln in enumerate(lines):
        match = _FINAL_PAT.search(ln)
        if not match:
            continue
        candidate = match.group(1).strip()
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
    # returns tuple: (normalized_text, numeric_or_None)
    from subprocess import Popen, PIPE
    try:
        p = Popen([sys.executable, str(BASE_DIR / "canonicalize.py")], stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)
        out, _ = p.communicate(ans, timeout=20)
        js = json.loads(out or "{}")
        if not js:
            return (ans.strip().lower(), None)
        return js.get("text", ans.strip().lower()), js.get("num")
    except Exception:
        # Fallback: simple lowercase and no number
        return (ans.strip().lower(), None)


def referee(question: str, candidate: str, model: str):
    prompt = f"{REFEREE_TMPL}\n\nCandidate Final Answer: {candidate}\n\nQuestion:\n{question}\n"
    resp = post_generate(model, prompt, CTX, REF_TEMP, 0.9, 700)
    text = resp.get("response","")
    path = RUNS / "referee.txt"
    if text:
        path.write_text(text)
    else:
        path.write_text(resp.get("error",""))
    if resp.get("error"):
        return ("UNKNOWN", text)
    m = re.search(r'(?i)^\s*verdict\s*[:\-]\s*(pass|fail)\s*$', text, re.M)
    return (m.group(1).upper() if m else "UNKNOWN"), text


def vote_tally(canon_pairs):
    """
    canon_pairs: list of (canon_text, numeric or None, raw)
    Returns (leader_keytype, leader_key, leader_count, totals, per_key_map)
    Key is numeric rounded (if majority have numbers), else canon_text.
    """
    nums = [x[1] for x in canon_pairs if x[1] is not None]
    by_num = {}
    if len(nums) >= max(3, len(canon_pairs)//2):  # numeric majority available
        for t, num, raw in canon_pairs:
            if num is None:
                continue
            key = f"{num:.10g}"  # stable rounding bucket
            by_num.setdefault(key, []).append(raw)
        if by_num:
            leader = max(by_num.items(), key=lambda kv: len(kv[1]))
            return ("NUM", leader[0], len(leader[1]), sum(len(v) for v in by_num.values()), by_num)
    # fallback to text
    by_txt = {}
    for t, num, raw in canon_pairs:
        by_txt.setdefault(t, []).append(raw)
    leader = max(by_txt.items(), key=lambda kv: len(kv[1]))
    return ("TXT", leader[0], len(leader[1]), sum(len(v) for v in by_txt.values()), by_txt)


def sample_wave(question, model, wave_idx, n):
    out = []
    threads = []
    lock = threading.Lock()

    def one(i):
        seed = random.randint(0, 2**31-1)
        prompt = f"{PROMPT_TMPL}\n\nQuestion:\n{question}\n"
        try:
            resp = post_generate(model, prompt, CTX, TEMP, TOP_P, PREDICT, seed)
        except Exception as exc:
            with lock:
                out.append(("", None, ""))
            (RUNS/f"{wave_idx}_{i}_error.txt").write_text(f"generation failed: {exc}")
            return
        text = resp.get("response","")
        path = RUNS/f"{wave_idx}_{i}.txt"
        path.write_text(text or resp.get("error",""))
        if resp.get("error"):
            with lock:
                out.append(("", None, ""))
            return
        ans = extract_final_answer(text)
        except Exception as e:
            text, ans = f"[ERROR] {e}", ""
        tcanon, ncanon = canonicalize(ans)
        with lock:
            out.append((tcanon, ncanon, ans))

    for i in range(n):
        th = threading.Thread(target=one, args=(i,))
        th.daemon = True
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    return out


def run(question):
    start = time.time()
    model = MODEL1
    wave = 0
    weighted_counts = collections.Counter()
    raw_store = collections.defaultdict(list)

    while True:
        left = TIME_BUDGET - int(time.time() - start)
        if left <= 0:
            break
        wave += 1
        # sample
        pairs = sample_wave(question, model, wave, BATCH)
        # vote
        keytype, leader_key, leader_cnt, total_cnt, map_ = vote_tally(pairs)
        # current leader raw example
        leader_raw = (map_.get(leader_key) or [""])[0]
        # referee
        verdict, rtext = referee(question, leader_key if keytype == "NUM" else leader_raw, model)
        # weight: votes + 0.5 bonus if referee PASS
        weight = leader_cnt + (0.5 if verdict == "PASS" else 0.0)
        weighted_counts[(keytype, leader_key)] += weight
        raw_store[(keytype, leader_key)].append(leader_raw)

        # confidence
        best_key, best_w = max(weighted_counts.items(), key=lambda kv: kv[1])
        tot_w = sum(weighted_counts.values())
        conf = (best_w / tot_w) if tot_w > 0 else 0.0

        # progress line
        print(f"[wave {wave:02d} | model={model}] leader={best_key} weight={best_w:.2f}/{tot_w:.2f} conf={conf:.2%} verdict={verdict} time_left={left}s")

        # stop if confident & verified
        if conf >= CONF and verdict == "PASS":
            final_key = best_key
            final_texts = raw_store[final_key]
            final = final_key[1] if final_key[0] == "NUM" else extract_final_answer(final_texts[0])
            return final, conf, model

        # weak consensus; consider fallback model on next wave
        if model == MODEL1 and MODEL2 and wave >= 2:
            model = MODEL2

        if time.time() - start > TIME_BUDGET:
            break

    # best effort
    if weighted_counts:
        final_key, final_w = max(weighted_counts.items(), key=lambda kv: kv[1])
        final_texts = raw_store.get(final_key, [""])
        final = final_key[1] if final_key[0] == "NUM" else (extract_final_answer(final_texts[0]) if final_texts else "UNKNOWN")
        conf = final_w / sum(weighted_counts.values())
    else:
        final = "UNKNOWN"
        conf = 0.0
    return final, conf, model


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 mjthinking_pro.py \"YOUR QUESTION\"")
        sys.exit(1)
    q = sys.argv[1]
    fin, conf, used_model = run(q)
    print("\n================== MJThinking PRO RESULT ==================")
    print(f"Final Answer: {fin}")
    print(f"Confidence (weighted): {conf:.2%}   Model: {used_model}")
    print("Traces saved in ./runs/")
    print("===========================================================\n")
