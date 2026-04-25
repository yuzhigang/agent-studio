from src.runtime.lib.decorator import lib_function

@lib_function()
def plan(args: dict) -> dict:
    return {"plan": args["target"]}
