import ast, math, re, sys

def safe_eval(expr: str):
    # Allow only numbers, operators, parens, and whitespace.
    # This is still not perfectly safe, but better.
    expr = expr.strip()
    if not re.fullmatch(r"[\d\s\.\+\-\*\/\%\(\)]+", expr):
        raise ValueError("Unsafe characters in expression")

    # Replace dangerous patterns
    if "__" in expr:
        raise ValueError("Double underscores are not allowed")

    # Use ast to parse and validate the expression
    tree = ast.parse(expr, mode='eval')
    allowed_nodes = {
        ast.Expression, ast.Constant, ast.Num, ast.BinOp, ast.UnaryOp,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Load
    }
    for node in ast.walk(tree):
        if type(node) not in allowed_nodes:
            raise ValueError(f"Disallowed operation: {type(node).__name__}")

    # The 'math' module is provided for functions like sqrt, etc.
    # The environment is cleared of builtins.
    return eval(compile(tree, "<string>", "eval"), {"__builtins__": {}, "math": math})

def extract_numeric(s: str):
    # Improved regex to find numbers, including scientific notation.
    # It prioritizes numbers at the end of the string.
    matches = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except (ValueError, IndexError):
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("UNKNOWN")
        sys.exit(0)

    question, candidate_answer = sys.argv[1], sys.argv[2]

    # Try to find a simple arithmetic expression in the question.
    # This is a weak spot, as questions can be complex.
    # "what is 4 * (2+3)" -> "4*(2+3)"
    expr_in_question = "".join(c for c in question if c in "0123456789.+-*/()% ")

    try:
        expected_value = safe_eval(expr_in_question)
    except Exception:
        print("UNKNOWN")
        sys.exit(0)

    actual_value = extract_numeric(candidate_answer)
    if actual_value is None:
        print("UNKNOWN")
        sys.exit(0)

    # Use a relative tolerance for floating point comparisons
    if math.isclose(expected_value, actual_value, rel_tol=1e-6, abs_tol=1e-9):
        print("PASS")
    else:
        print("FAIL")