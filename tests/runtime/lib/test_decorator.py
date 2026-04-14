from src.runtime.lib.decorator import lib_function

def test_decorator_attaches_metadata():
    @lib_function(name="getCandidates", namespace="ladle", readonly=True)
    def get_candidates(args: dict) -> dict:
        return {"ok": True}

    assert hasattr(get_candidates, "_lib_meta")
    assert get_candidates._lib_meta["name"] == "getCandidates"
    assert get_candidates._lib_meta["namespace"] == "ladle"
    assert get_candidates._lib_meta["readonly"] is True
    assert get_candidates._lib_meta["entrypoint"] == "get_candidates"

def test_decorator_defaults():
    @lib_function(name="doWork", namespace="shared")
    def do_work(args: dict) -> dict:
        return {}

    assert do_work._lib_meta["readonly"] is False
