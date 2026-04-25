import os
import pytest
from src.runtime.lib import (
    LibRegistry,
    LibProxy,
    SandboxExecutor,
    lib_function,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")

def test_full_dsl_run_script(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)

    script = """
result = lib.dispatcher.getCandidates({'converterId': args['converterId']})
"""
    executor = SandboxExecutor()
    result = executor.execute(script, {
        "args": {"converterId": "C01"},
        "lib": proxy,
    })
    assert result == {"candidates": []}

def test_cross_namespace_call_rejected(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)

    script = "result = lib.machines.converter.planner.plan({'target': 'A1'})"
    executor = SandboxExecutor()
    with pytest.raises(Exception, match="cross-agent"):
        executor.execute(script, {"lib": proxy})


def test_shared_modules_injected_into_sandbox(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))

    script = "result = api.echo({'message': 'hello from sandbox'})"
    executor = SandboxExecutor(registry=registry)
    result = executor.execute(script, {})
    assert result == {"message": "hello from sandbox"}


def test_shared_modules_can_be_imported_in_sandbox(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))

    script = """
import api
result = api.httpGet({'url': 'https://example.com'})
"""
    executor = SandboxExecutor(registry=registry)
    result = executor.execute(script, {})
    assert result["method"] == "GET"
    assert result["url"] == "https://example.com"
    assert result["status"] == 200
    assert "data" in result


def test_all_shared_libs_are_preloaded(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))

    script = """
import api
import utils
result = {
    'api': api.echo({'message': 'hi'}),
    'utils': utils.uppercase({'text': 'hello'}),
}
"""
    executor = SandboxExecutor(registry=registry)
    result = executor.execute(script, {})
    assert result == {
        "api": {"message": "hi"},
        "utils": {"text": "HELLO"},
    }


def test_ladle_dispatcher_get_candidates(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="roles.ladle_dispatcher", registry=registry)

    script = """
result = lib.ladle.getCandidates({
    'grade': 'Q235B',
    'heat_id': 'H2025041401',
    'order_id': 'ORD-001',
    'tonnage': 260,
    'top_k': 2,
})
"""
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})
    assert result["grade"] == "Q235B"
    assert result["heat_id"] == "H2025041401"
    assert result["count"] == 2
    assert len(result["candidates"]) == 2
    for c in result["candidates"]:
        assert "ladle_id" in c
        assert "score" in c
