from math import ceil, cos, e, factorial, floor, log, log10, log2, pi, pow, sin, sqrt, tan


ALLOWED_NAMES = {
    "sqrt": sqrt,
    "sin": sin,
    "cos": cos,
    "tan": tan,
    "log": log,
    "log2": log2,
    "log10": log10,
    "pow": pow,
    "floor": floor,
    "ceil": ceil,
    "abs": abs,
    "round": round,
    "pi": pi,
    "e": e,
    "factorial": factorial,
}


def calculate(expression: str) -> dict:
    if len(expression) > 200:
        return {"error": "Expression too long"}

    try:
        result = eval(expression, {"__builtins__": {}}, ALLOWED_NAMES)
        return {"expression": expression, "result": result}
    except ZeroDivisionError:
        return {"error": "Division by zero"}
    except NameError:
        return {"error": "Invalid expression"}
    except Exception:
        return {"error": "Could not evaluate expression"}
