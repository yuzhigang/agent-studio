import pytest
from src.runtime.triggers.condition_trigger import (
    _extract_condition_deps, ConditionTrigger, ConditionIndex,
)
from src.runtime.trigger_registry import TriggerEntry


def test_extract_condition_deps_parses_this_paths():
    expr = "this.variables.temperature >= this.attributes.threshold"
    deps = _extract_condition_deps(expr)
    assert sorted(deps) == ["attributes.threshold", "variables.temperature"]


def test_extract_condition_deps_ignores_non_property_sections():
    expr = "this.metadata.name == 'x' and this.variables.count > 0"
    deps = _extract_condition_deps(expr)
    assert deps == ["variables.count"]


def test_condition_index_registers_and_queries():
    idx = ConditionIndex()
    entry = type("E", (), {"watch": ["variables.temperature", "attributes.threshold"]})
    idx.register(entry)

    affected = idx.get_affected({"variables.temperature"})
    assert affected == [entry]

    affected = idx.get_affected({"variables.pressure"})
    assert affected == []


def test_condition_trigger_evaluates_true():
    ct = ConditionTrigger(sandbox=None)
    calls = []
    inst = type("Inst", (), {
        "variables": {"temperature": 90},
        "attributes": {"threshold": 80},
    })()
    entry = TriggerEntry(
        inst,
        {
            "type": "condition",
            "name": "overheat",
            "condition": "this.variables.temperature >= this.attributes.threshold",
        },
        lambda i: calls.append(i),
        "b1",
    )
    ct.on_registered(entry)

    ct.handle_value_change(inst, "variables.temperature", 70, 90)
    assert len(calls) == 1
    assert calls[0] is inst


def test_condition_trigger_evaluates_false():
    ct = ConditionTrigger(sandbox=None)
    calls = []
    inst = type("Inst", (), {
        "variables": {"temperature": 60},
        "attributes": {"threshold": 80},
    })()
    entry = TriggerEntry(
        inst,
        {
            "type": "condition",
            "name": "overheat",
            "condition": "this.variables.temperature >= this.attributes.threshold",
        },
        lambda i: calls.append(i),
        "b1",
    )
    ct.on_registered(entry)

    ct.handle_value_change(inst, "variables.temperature", 70, 60)
    assert len(calls) == 0


def test_condition_trigger_ignores_unrelated_field():
    ct = ConditionTrigger(sandbox=None)
    calls = []
    inst = type("Inst", (), {
        "variables": {"temperature": 90, "pressure": 10},
        "attributes": {"threshold": 80},
    })()
    entry = TriggerEntry(
        inst,
        {
            "type": "condition",
            "name": "overheat",
            "condition": "this.variables.temperature >= this.attributes.threshold",
        },
        lambda i: calls.append(i),
        "b1",
    )
    ct.on_registered(entry)

    ct.handle_value_change(inst, "variables.pressure", 5, 10)
    assert len(calls) == 0
