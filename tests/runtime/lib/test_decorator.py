from src.runtime.lib.decorator import lib_function

def test_decorator_attaches_metadata():
    @lib_function(name="getCandidates", module="dispatcher")
    def get_candidates(args: dict) -> dict:
        return {"ok": True}

    assert hasattr(get_candidates, "_lib_meta")
    assert get_candidates._lib_meta["name"] == "getCandidates"
    assert get_candidates._lib_meta["module"] == "dispatcher"
    assert get_candidates._lib_meta["entrypoint"] == "get_candidates"

def test_decorator_defaults():
    @lib_function()
    def do_work(args: dict) -> dict:
        return {}

    assert do_work._lib_meta["name"] is None
    assert do_work._lib_meta["module"] is None
    assert do_work._lib_meta["entrypoint"] == "do_work"


def test_decorator_normalizes_empty_name_and_module_to_none():
    @lib_function(name="", module="")
    def do_work(args: dict) -> dict:
        return {}

    assert do_work._lib_meta["name"] is None
    assert do_work._lib_meta["module"] is None
