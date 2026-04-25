import os
import pytest
from src.runtime.lib import (
    LibRegistry,
    LibProxy,
    SandboxExecutor,
)
from src.runtime.lib.exceptions import ScriptExecutionError
from src.runtime.instance import Instance
from src.runtime.instance_manager import InstanceManager

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")

def test_full_dsl_run_script(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)

    script = """
result = lib.dispatcher.get_candidates({'converterId': args['converterId']})
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


def test_shared_modules_can_be_imported_in_sandbox(registry: LibRegistry, monkeypatch):
    registry.scan(os.path.join(FIXTURES, "agents"))

    class _FakeResponse:
        status = 200
        headers = {"Content-Type": "text/plain"}

        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse())

    script = """
import api
result = api.http_get({'url': 'https://example.com'})
"""
    executor = SandboxExecutor(registry=registry)
    result = executor.execute(script, {})
    assert result["method"] == "GET"
    assert result["url"] == "https://example.com"
    assert result["status"] == 200
    assert "data" in result


def test_sandbox_rejects_agent_specific_import_even_when_registry_loaded(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))

    executor = SandboxExecutor(registry=registry)

    with pytest.raises(ScriptExecutionError, match="Import of 'dispatcher' is not allowed"):
        executor.execute("import dispatcher", {})


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


def test_sandbox_rejects_shared_module_name_collision(registry: LibRegistry):
    registry._data["shared.json.echo"] = lambda args: args

    executor = SandboxExecutor(registry=registry)

    with pytest.raises(ScriptExecutionError, match="collides with preloaded module"):
        executor.execute("result = 1", {})


def test_ladle_dispatcher_get_candidates(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="roles.ladle_dispatcher", registry=registry)

    script = """
result = lib.ladle.get_candidates({
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


def test_behavior_context_lib_proxy_uses_agent_namespace_over_model_name(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    manager = InstanceManager(sandbox_executor=SandboxExecutor(registry=registry))
    instance = Instance(
        instance_id="ladle-01",
        model_name="ladle",
        world_id="world-01",
        scope="world",
        _agent_namespace="logistics.ladle",
    )

    context = manager._build_behavior_context(instance, payload={}, source="test")

    script = """
result = lib.dispatcher.get_candidates({'converterId': 'C01'})
"""
    result = manager._sandbox.execute(script, context)
    assert result == {"candidates": []}
