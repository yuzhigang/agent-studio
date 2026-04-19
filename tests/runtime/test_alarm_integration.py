import time

import pytest

from src.runtime.world_registry import WorldRegistry


@pytest.fixture
def registry(tmp_path):
    base = tmp_path / "worlds"
    base.mkdir()
    reg = WorldRegistry(base_dir=str(base), global_model_paths=[])
    reg.create_world("test-world")
    yield reg
    reg.unload_world("test-world")


def test_load_world_creates_alarm_manager(registry):
    bundle = registry.load_world("test-world")
    assert "alarm_manager" in bundle
    assert bundle["alarm_manager"] is not None
    assert bundle["instance_manager"]._alarm_manager is bundle["alarm_manager"]


def test_instance_manager_calls_alarm_manager_on_create(registry):
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.instance_manager import InstanceManager
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger
    from src.runtime.triggers.value_changed_trigger import ValueChangedTrigger
    from src.runtime.triggers.condition_trigger import ConditionTrigger
    from src.runtime.triggers.timer_trigger import TimerTrigger
    from src.runtime.event_bus import EventBusRegistry

    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    tr = TriggerRegistry()
    tr.add_trigger(EventTrigger(bus_reg))
    tr.add_trigger(ValueChangedTrigger())
    tr.add_trigger(ConditionTrigger(im._sandbox))
    tr.add_trigger(TimerTrigger())
    im._trigger_registry = tr

    alarm_mgr = AlarmManager(tr, bus_reg.get_or_create("w1"))
    im._alarm_manager = alarm_mgr

    model = {
        "alarms": {
            "testAlarm": {
                "category": "test",
                "title": "Test",
                "severity": "warning",
                "trigger": {"type": "event", "name": "test"},
            }
        }
    }
    inst = im.create("w1", "m1", "i1", model=model)
    assert len(alarm_mgr._trigger_ids) == 1

    im.remove("w1", "i1")
    assert len(alarm_mgr._trigger_ids) == 0


def test_instance_manager_unregisters_alarms_on_archive():
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.instance_manager import InstanceManager
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger
    from src.runtime.triggers.value_changed_trigger import ValueChangedTrigger
    from src.runtime.triggers.condition_trigger import ConditionTrigger
    from src.runtime.triggers.timer_trigger import TimerTrigger
    from src.runtime.event_bus import EventBusRegistry

    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    tr = TriggerRegistry()
    tr.add_trigger(EventTrigger(bus_reg))
    tr.add_trigger(ValueChangedTrigger())
    tr.add_trigger(ConditionTrigger(im._sandbox))
    tr.add_trigger(TimerTrigger())
    im._trigger_registry = tr

    alarm_mgr = AlarmManager(tr, bus_reg.get_or_create("w1"))
    im._alarm_manager = alarm_mgr

    model = {
        "alarms": {
            "testAlarm": {
                "category": "test",
                "title": "Test",
                "severity": "warning",
                "trigger": {"type": "event", "name": "test"},
            }
        }
    }
    inst = im.create("w1", "m1", "i1", model=model)
    assert len(alarm_mgr._trigger_ids) == 1

    im.transition_lifecycle("w1", "i1", "archived")
    assert len(alarm_mgr._trigger_ids) == 0


def test_alarm_triggered_via_condition():
    """End-to-end: load demo-world, trigger alarm via tick event, verify alarm state."""
    registry = WorldRegistry(base_dir="worlds", global_model_paths=["agents"])
    bundle = registry.load_world("demo-world")

    im = bundle["instance_manager"]
    bus = bundle["event_bus_registry"].get_or_create("demo-world")
    alarm_mgr = bundle["alarm_manager"]

    inst = im.get("demo-world", "sensor-01", scope="world")
    assert inst is not None

    # Start monitoring so condition trigger is relevant
    bus.publish("start", {}, source="test", scope="world")
    time.sleep(0.1)
    assert inst.state.get("current") == "monitoring"

    # Send temperature above threshold
    bus.publish("tick", {"temperature": 95.0}, source="test", scope="world")
    time.sleep(0.2)

    # Verify alarm is active
    state = alarm_mgr._get_state(inst, "overheat.warning")
    assert state.state == "active"
    assert state.trigger_count >= 1

    # Verify temperature updated
    assert inst.variables.get("temperature") == 95.0

    # Reset — temperature drops to 25, condition false, alarm clears
    bus.publish("reset", {}, source="test", scope="world")
    time.sleep(0.1)

    # Alarm should be inactive after reset
    state = alarm_mgr._get_state(inst, "overheat.warning")
    assert state.state == "inactive"

    registry.unload_world("demo-world")
