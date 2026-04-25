from src.runtime.lib.decorator import lib_function

@lib_function()
def get_candidates(args: dict) -> dict:
    return {"candidates": []}
