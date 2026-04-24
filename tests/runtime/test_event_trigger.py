import pytest
from src.runtime.event_bus import EventBusRegistry
from src.runtime.triggers.event_trigger import EventTrigger
from src.runtime.trigger_registry import TriggerEntry


def test_event_trigger_callbacks_on_matching_event():
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("w1")
    et = EventTrigger(bus_reg)

    calls = []
    inst = {"id": "i1", "world_id": "w1", "scope": "world"}
    entry = TriggerEntry(inst, {"type": "event", "name": "start"}, lambda i, **kw: calls.append(i), "b1")
    et.on_registered(entry)

    bus.publish("start", {"foo": 1}, source="ext", scope="world")
    assert len(calls) == 1
    assert calls[0] is inst


def test_event_trigger_skips_non_matching_event():
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("w1")
    et = EventTrigger(bus_reg)

    calls = []
    inst = {"id": "i1", "world_id": "w1", "scope": "world"}
    entry = TriggerEntry(inst, {"type": "event", "name": "start"}, lambda i, **kw: calls.append(i), "b1")
    et.on_registered(entry)

    bus.publish("stop", {}, source="ext", scope="world")
    assert len(calls) == 0


def test_event_trigger_respects_scope():
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("w1")
    et = EventTrigger(bus_reg)

    calls = []
    inst = {"id": "i1", "world_id": "w1", "scope": "scene:s1"}
    entry = TriggerEntry(inst, {"type": "event", "name": "start"}, lambda i, **kw: calls.append(i), "b1")
    et.on_registered(entry)

    # world-scoped messages broadcast to all instances
    bus.publish("start", {}, source="ext", scope="world")
    assert len(calls) == 1
    calls.clear()

    # matching scene message is received
    bus.publish("start", {}, source="ext", scope="scene:s1")
    assert len(calls) == 1
    calls.clear()

    # non-matching scene message is not received
    bus.publish("start", {}, source="ext", scope="scene:s2")
    assert len(calls) == 0


def test_event_trigger_unregistered_stops_receiving():
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("w1")
    et = EventTrigger(bus_reg)

    calls = []
    inst = {"id": "i1", "world_id": "w1", "scope": "world"}
    entry = TriggerEntry(inst, {"type": "event", "name": "start"}, lambda i, **kw: calls.append(i), "b1")
    et.on_registered(entry)
    et.on_unregistered(entry)

    bus.publish("start", {}, source="ext", scope="world")
    assert len(calls) == 0


def test_event_trigger_removes_instance():
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("w1")
    et = EventTrigger(bus_reg)

    calls = []
    inst = {"id": "i1", "world_id": "w1", "scope": "world"}
    entry = TriggerEntry(inst, {"type": "event", "name": "start"}, lambda i, **kw: calls.append(i), "b1")
    et.on_registered(entry)
    et.on_instance_removed(inst)

    bus.publish("start", {}, source="ext", scope="world")
    assert len(calls) == 0


def test_event_trigger_removes_only_same_instance():
    """Verify that removing one instance does not affect other instances' handlers."""
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("w1")
    et = EventTrigger(bus_reg)

    calls_a = []
    calls_b = []
    inst_a = {"id": "i1", "world_id": "w1", "scope": "world"}
    inst_b = {"id": "i2", "world_id": "w1", "scope": "world"}
    entry_a = TriggerEntry(inst_a, {"type": "event", "name": "start"}, lambda i, **kw: calls_a.append(i), "b1")
    entry_b = TriggerEntry(inst_b, {"type": "event", "name": "start"}, lambda i, **kw: calls_b.append(i), "b2")
    et.on_registered(entry_a)
    et.on_registered(entry_b)

    # Remove only instance A
    et.on_instance_removed(inst_a)

    # Instance B should still receive events
    bus.publish("start", {}, source="ext", scope="world")
    assert len(calls_a) == 0
    assert len(calls_b) == 1
    assert calls_b[0] is inst_b
