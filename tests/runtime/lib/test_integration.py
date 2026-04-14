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
    proxy = LibProxy(default_namespace="ladle", registry=registry)

    script = """
result = lib.dispatcher.getCandidates({'converterId': args['converterId']})
"""
    executor = SandboxExecutor()
    result = executor.execute(script, {
        "args": {"converterId": "C01"},
        "lib": proxy,
    })
    assert result == {"candidates": []}

def test_cross_namespace_call(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="ladle", registry=registry)

    script = "result = lib.converter.planner.plan({'target': 'A1'})"
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})
    assert result == {"plan": "A1"}
