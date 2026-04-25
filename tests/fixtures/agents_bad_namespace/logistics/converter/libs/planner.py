from src.runtime.lib.decorator import lib_function

@lib_function(name="plan", namespace="wrong")
def plan(args: dict) -> dict:
    return {}
