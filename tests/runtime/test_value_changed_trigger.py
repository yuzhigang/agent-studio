import pytest
from src.runtime.triggers.value_changed_trigger import ValueChangedTrigger
from src.runtime.trigger_registry import TriggerEntry


def test_value_changed_matches_exact_value():
    vct = ValueChangedTrigger()
    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "valueChanged", "name": "state.current", "value": "monitoring"},
        lambda i: calls.append(i),
        "b1",
    )
    vct.on_registered(entry)

    vct.handle_value_change(inst, "state.current", "idle", "monitoring")
    assert len(calls) == 1
    assert calls[0] is inst


def test_value_changed_no_value_matches_any_change():
    vct = ValueChangedTrigger()
    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "valueChanged", "name": "variables.temperature"},
        lambda i: calls.append(i),
        "b1",
    )
    vct.on_registered(entry)

    vct.handle_value_change(inst, "variables.temperature", 20, 25)
    assert len(calls) == 1
    assert calls[0] is inst


def test_value_changed_skips_wrong_field():
    vct = ValueChangedTrigger()
    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "valueChanged", "name": "state.current", "value": "monitoring"},
        lambda i: calls.append(i),
        "b1",
    )
    vct.on_registered(entry)

    vct.handle_value_change(inst, "variables.temperature", 20, 25)
    assert len(calls) == 0


def test_value_changed_skips_wrong_target_value():
    vct = ValueChangedTrigger()
    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "valueChanged", "name": "state.current", "value": "monitoring"},
        lambda i: calls.append(i),
        "b1",
    )
    vct.on_registered(entry)

    vct.handle_value_change(inst, "state.current", "idle", "alert")
    assert len(calls) == 0


def test_value_changed_unregistered():
    vct = ValueChangedTrigger()
    calls = []
    inst = object()
    entry = TriggerEntry(
        inst,
        {"type": "valueChanged", "name": "state.current", "value": "monitoring"},
        lambda i: calls.append(i),
        "b1",
    )
    vct.on_registered(entry)
    vct.on_unregistered(entry)

    vct.handle_value_change(inst, "state.current", "idle", "monitoring")
    assert len(calls) == 0
