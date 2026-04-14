from src.runtime.lib.decorator import lib_function

@lib_function(name="getCandidates", namespace="ladle", readonly=True)
def get_candidates(args: dict) -> dict:
    return {"candidates": []}
