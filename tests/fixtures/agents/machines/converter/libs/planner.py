from src.runtime.lib.decorator import lib_function

@lib_function(name="plan", namespace="machines.converter")
def plan(args: dict) -> dict:
    return {"plan": args["target"]}
