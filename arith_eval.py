import ast, math, re, sys

def safe_eval(expr: str):
    # allow only numbers, + - * / // % ** ( ) . , and whitespace
    if not re.fullmatch(r"[0-9\.\s\+\-\*\/\%\(\)\,]+", expr):
        raise ValueError("unsafe chars")
    node = ast.parse(expr, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
               ast.Pow, ast.USub, ast.UAdd, ast.Tuple)
    for n in ast.walk(node):
        if not isinstance(n, allowed):
            raise ValueError("bad node")
    return eval(compile(node, "<expr>", "eval"), {"__builtins__": {}}, {"math": math})

def extract_numeric(s: str):
    # pick last numeric token in the final answer line
    m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
    if not m: return None
    return float(m[-1])

if __name__ == "__main__":
    # argv: question  candidate_final_line
    if len(sys.argv) < 3:
        print("UNKNOWN")
        sys.exit(0)

    q, cand = sys.argv[1], sys.argv[2]
    # Try to find a simple arithmetic expression in the question
    qexpr = "".join(ch for ch in q if ch in "0123456789.+-*/()% ,")
    try:
        qexpr_val = safe_eval(qexpr)
    except Exception:
        print("UNKNOWN"); sys.exit(0)

    ans = extract_numeric(cand)
    if ans is None:
        print("UNKNOWN"); sys.exit(0)

    # Loose numeric match tolerance
    if abs(qexpr_val - ans) <= max(1e-9, 1e-6*abs(qexpr_val)):
        print("PASS")
    else:
        print("FAIL")
