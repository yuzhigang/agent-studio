import pytest
from src.simulator.scripting import SimContext, Event, run_script


def test_context_state():
    ctx = SimContext()
    ctx.set("alerting", True)
    assert ctx.get("alerting") is True
    assert ctx.get("missing") is None
    assert ctx.get("missing", "default") == "default"


def test_event_creation():
    evt = Event("tick", {"temperature": 85})
    assert evt.event_type == "tick"
    assert evt.payload == {"temperature": 85}


def test_run_simple_script():
    script = """
def on_tick(ctx):
    return Event("tick", {"temperature": 85})
"""
    ctx = SimContext()
    result = run_script(script, "on_tick", ctx)
    assert isinstance(result, Event)
    assert result.event_type == "tick"


def test_script_forbidden_import():
    script = """
import os
def on_tick(ctx):
    return Event("tick", {})
"""
    ctx = SimContext()
    with pytest.raises(ImportError):
        run_script(script, "on_tick", ctx)


def test_context_distributions():
    ctx = SimContext(seed=42)

    val = ctx.gaussian(0, 1)
    assert isinstance(val, float)

    val = ctx.uniform(0, 10)
    assert 0 <= val <= 10

    val = ctx.randint(1, 6)
    assert 1 <= val <= 6

    val = ctx.exponential(1.0)
    assert val >= 0

    val = ctx.triangular(0, 10, 5)
    assert 0 <= val <= 10

    val = ctx.lognormal(0, 1)
    assert val > 0

    val = ctx.pareto(1.0)
    assert val >= 1

    val = ctx.weibull(1.0, 1.0)
    assert val >= 0


def test_run_script_with_distributions():
    script = """
def on_tick(ctx):
    temp = ctx.gaussian(60, 20)
    delay = ctx.exponential(0.5)
    return Event("tick", {"temperature": temp, "delay": delay})
"""
    ctx = SimContext()
    result = run_script(script, "on_tick", ctx)
    assert isinstance(result, Event)
    assert "temperature" in result.payload
    assert "delay" in result.payload
