import re, sys, json
def strip_md(s: str) -> str:
    return re.sub(r'[*`_]', '', s or '').strip()
def last_number(s: str):
    m = re.findall(r'[-+]?\d+(?:[,\s]\d{3})*(?:\.\d+)?', s or '')
    if not m: return None
    t = m[-1].replace(',', '').replace(' ', '')
    try: return float(t)
    except: return None
def canon_text(s: str) -> str:
    s = strip_md(s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[ \t]+([,.;:!?])', r'\1', s)
    return s.lower().strip()
if __name__ == "__main__":
    s = sys.stdin.read()
    print(json.dumps({"raw": s, "text": canon_text(s), "num": last_number(s)}))
