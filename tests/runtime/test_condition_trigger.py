import pytest
from src.runtime.triggers.condition_trigger import (
    _extract_condition_deps, ConditionTrigger,
)
from src.runtime.trigger_registry import TriggerEntry, DependencyIndex


def test_extract_condition_deps_parses_this_paths():
    expr = "this.variables.temperature >= this.attributes.threshold"
    deps = _extract_condition_deps(expr)
    assert sorted(deps) == ["attributes.threshold", "variables.temperature"]


def test_extract_condition_deps_ignores_non_property_sections():
    expr = "this.metadata.name == 'x' and this.variables.count > 0"
    deps = _extract_condition_deps(expr)
    assert deps == ["variables.count"]


def test_dependency_index_routes_by_field_path():
    idx = DependencyIndex()
    entry = type("E", (), {"id": "1", "instance": "inst-1", "watch": ["variables.temperature"]})()
    idx.register(entry)

    affected = idx.get_affected("variables.temperature", "inst-1")
    assert affected == [entry]

    affected = idx.get_affected("variables.pressure", "inst-1")
    assert affected == []


def test_dependency_index_filters_by_instance():
    idx = DependencyIndex()
    e1 = type("E", (), {"id": "1", "instance": "inst-1", "watch": ["variables.temperature"]})()
    e2 = type("E", (), {"id": "2", "instance": "inst-2", "watch": ["variables.temperature"]})()
    idx.register(e1)
    idx.register(e2)

    affected = idx.get_affected("variables.temperature", "inst-1")
    assert affected == [e1]
    assert e2 not in affected


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

    ct.handle_value_change(entry, inst, "variables.temperature", 70, 90)
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

    ct.handle_value_change(entry, inst, "variables.temperature", 70, 60)
    assert len(calls) == 0
