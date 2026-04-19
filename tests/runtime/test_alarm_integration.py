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
