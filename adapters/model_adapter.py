import os
import json
import urllib.request
import urllib.error

def _openai_base(api: str) -> str:
    base = (api or "").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base

def generate(model: str, prompt: str, ctx: int, temperature: float, top_p: float, num_predict: int, api: str, api_type: str, api_key: str = None, seed: int = None, timeout: int = None):
    api_type = (api_type or "").lower()
    timeout = timeout or max(600, int(num_predict) * 2)
    if api_type == "openai":
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "max_tokens": int(num_predict),
            "n": 1,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{_openai_base(api)}/completions", data=data, headers={"Content-Type": "application/json"})
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
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
            return {"response": "", "error": f"URLError: {getattr(e, 'reason', str(e))}", "raw": None}
        choice = (raw.get("choices") or [{}])[0]
        text = choice.get("text") or (choice.get("message") or {}).get("content") or raw.get("output_text", "")
        return {"response": text, "choices": raw.get("choices"), "usage": raw.get("usage"), "raw": raw}
    else:
        data = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": int(ctx),
                "temperature": float(temperature),
                "top_p": float(top_p),
                "num_predict": int(num_predict),
            },
        }
        if seed is not None:
            data["options"]["seed"] = int(seed)
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(f"{api}/api/generate", data=body, headers={"Content-Type": "application/json"})
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
            return {"response": "", "error": f"URLError: {getattr(e, 'reason', str(e))}", "raw": None}
        text = raw.get("response") or ""
        return {"response": text, "raw": raw}

