import pytest
from src.runtime.lib.sandbox import SandboxExecutor, SAFE_BUILTINS
from src.runtime.lib.exceptions import ScriptExecutionError, ImmutableContextError


def test_sandbox_executes_simple_script():
    executor = SandboxExecutor()
    result = executor.execute("a = 1 + 2\nresult = a * 3", {"args": {"x": 1}})
    assert result == 9


def test_sandbox_can_import_whitelisted_module():
    executor = SandboxExecutor()
    result = executor.execute("import math\nresult = math.ceil(2.3)", {})
    assert result == 3


def test_sandbox_blocks_non_whitelisted_import():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("import os\nresult = 1", {})


def test_sandbox_blocks_open():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("open('foo.txt')", {})


def test_sandbox_blocks_eval():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("eval('1+1')", {})


def test_sandbox_blocks_compile():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("compile('1+1', '<string>', 'eval')", {})


def test_sandbox_blocks_getattr():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("getattr({}, 'keys')", {})


def test_safe_builtins_has_math():
    assert "abs" in SAFE_BUILTINS
    assert "open" not in SAFE_BUILTINS


def test_sandbox_dispatch_publishes_event():
    from src.runtime.event_bus import EventBusRegistry

    registry = EventBusRegistry()
    bus = registry.get_or_create("world-01")
    received = []
    bus.register("ladle-001", "world", "ladleLoaded", lambda t, p, s: received.append((t, p, s)))

    executor = SandboxExecutor()
    context = {
        "this": {"id": "ladle-001", "world_id": "world-01"},
        "dispatch": lambda event_type, payload, target=None: bus.publish(
            event_type, payload, source="ladle-001", scope="world", target=target
        ),
    }
    executor.execute('dispatch("ladleLoaded", {"steelAmount": 180})', context)
    assert len(received) == 1
    assert received[0][0] == "ladleLoaded"
    assert received[0][1] == {"steelAmount": 180}
