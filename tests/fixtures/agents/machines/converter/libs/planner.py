from src.runtime.lib.decorator import lib_function

@lib_function(name="plan", namespace="converter", readonly=True)
def plan(args: dict) -> dict:
    return {"plan": args["target"]}
