import random
from dataclasses import dataclass
from typing import Any

SAFE_MODULES = {"math", "random", "datetime", "json", "collections"}


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: dict
    scope: str = "world"
    target: str | None = None


class SimContext:
    """Per-source isolated execution context."""
    def __init__(self, seed: int | None = None):
        self._state: dict[str, Any] = {}
        self._rng = random.Random(seed)

    def gaussian(self, mean: float, std: float) -> float:
        return self._rng.gauss(mean, std)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def exponential(self, rate: float) -> float:
        return self._rng.expovariate(rate)

    def triangular(self, low: float, high: float, mode: float) -> float:
        return self._rng.triangular(low, high, mode)

    def lognormal(self, mu: float, sigma: float) -> float:
        return self._rng.lognormvariate(mu, sigma)

    def pareto(self, alpha: float) -> float:
        return self._rng.paretovariate(alpha)

    def weibull(self, alpha: float, beta: float) -> float:
        return self._rng.weibullvariate(alpha, beta)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)


def _safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):
    if name not in SAFE_MODULES and not name.startswith("simulator."):
        raise ImportError(f"Import of '{name}' is not allowed in simulator scripts")
    return __import__(name, globals, locals, fromlist, level)


def run_script(script_code: str, function_name: str, ctx: SimContext) -> Event | None:
    """Execute user script in a restricted environment."""
    safe_builtins = {
        "__import__": _safe_import,
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "float": float, "int": int, "len": len, "list": list, "max": max,
        "min": min, "pow": pow, "print": print, "range": range,
        "round": round, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip,
    }
    env = {"__builtins__": safe_builtins, "Event": Event, "Context": SimContext}
    exec(script_code, env)
    func = env.get(function_name)
    if func is None:
        return None
    return func(ctx)
