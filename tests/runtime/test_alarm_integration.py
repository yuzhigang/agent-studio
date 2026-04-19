import time

import pytest

from src.runtime.world_registry import WorldRegistry


def test_alarm_persisted_to_database(tmp_path):
    """End-to-end: trigger alarm, verify record in SQLite, clear alarm, verify state."""
    from src.runtime.stores.sqlite_store import SQLiteStore

    # Create a minimal ephemeral world
    world_dir = tmp_path / "test-world"
    world_dir.mkdir()
    store = SQLiteStore(str(world_dir))

    # Manually wire up an AlarmManager with this store
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.event_bus import EventBusRegistry

    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("test-world")
    am = AlarmManager(trigger_registry=None, event_bus=bus, store=store)

    class FakeInst:
        def __init__(self):
            self.instance_id = "sensor-01"
            self.world_id = "test-world"
            self.id = "sensor-01"
            self.variables = {"temperature": 95.0, "threshold": 80.0}
            self.attributes = {}
            self.state = {"current": "monitoring"}
            self.model = {
                "alarms": {
                    "overheat.warning": {
                        "category": "overheat",
                        "severity": "warning",
                        "level": 1,
                        "triggerMessage": "温度 {temperature}℃ 超过阈值 {threshold}℃",
                        "clearMessage": "温度已恢复正常",
                    }
                }
            }

    inst = FakeInst()
    config = inst.model["alarms"]["overheat.warning"]

    # Trigger alarm
    am._on_trigger(inst, "overheat.warning", config)

    # Verify DB record
    record = store.load_alarm("test-world", "sensor-01", "overheat.warning")
    assert record is not None
    assert record["state"] == "active"
    assert record["trigger_count"] == 1
    assert record["trigger_message"] == "温度 95.0℃ 超过阈值 80.0℃"
    assert record["severity"] == "warning"
    assert record["payload"] == {"temperature": 95.0, "threshold": 80.0}

    # Clear alarm
    am._on_clear(inst, "overheat.warning", config)

    # Verify DB record updated
    record = store.load_alarm("test-world", "sensor-01", "overheat.warning")
    assert record["state"] == "inactive"
    assert record["cleared_at"] is not None
    assert record["trigger_count"] == 0  # reset on clear


def test_alarm_time_range_query(tmp_path):
    from src.runtime.stores.sqlite_store import SQLiteStore
    from src.runtime.alarm_manager import AlarmManager

    world_dir = tmp_path / "test-world"
    world_dir.mkdir()
    store = SQLiteStore(str(world_dir))
    am = AlarmManager(None, None, store)

    class FakeInst:
        def __init__(self, iid):
            self.instance_id = iid
            self.world_id = "test-world"
            self.id = iid
            self.variables = {"temperature": 90.0 + int(iid[-2:])}
            self.attributes = {}
            self.state = {}
            self.model = {}

    # Create two alarms
    inst1 = FakeInst("s01")
    inst2 = FakeInst("s02")
    am._on_trigger(inst1, "a1", {"severity": "warning", "triggerMessage": "hot {temperature}"})
    am._on_trigger(inst2, "a2", {"severity": "warning", "triggerMessage": "hot {temperature}"})

    # List all alarms
    all_alarms = store.list_alarms("test-world")
    assert len(all_alarms) == 2

    # Filter by instance
    s01_alarms = store.list_alarms("test-world", instance_id="s01")
    assert len(s01_alarms) == 1
    assert s01_alarms[0]["alarm_id"] == "a1"

    # Filter by state
    active_alarms = store.list_alarms("test-world", state="active")
    assert len(active_alarms) == 2


def test_force_clear_via_store(tmp_path):
    from src.runtime.stores.sqlite_store import SQLiteStore
    from src.runtime.alarm_manager import AlarmManager
    from src.runtime.event_bus import EventBusRegistry

    world_dir = tmp_path / "test-world"
    world_dir.mkdir()
    store = SQLiteStore(str(world_dir))
    bus_reg = EventBusRegistry()
    bus = bus_reg.get_or_create("test-world")
    am = AlarmManager(None, bus, store)

    class FakeInst:
        def __init__(self):
            self.instance_id = "s01"
            self.world_id = "test-world"
            self.id = "s01"
            self.variables = {"temperature": 95.0}
            self.attributes = {}
            self.state = {}
            self.model = {
                "alarms": {
                    "a1": {
                        "severity": "warning",
                        "triggerMessage": "hot {temperature}",
                        "clearMessage": "cool",
                    }
                }
            }

    inst = FakeInst()
    config = inst.model["alarms"]["a1"]
    am._on_trigger(inst, "a1", config)

    record = store.load_alarm("test-world", "s01", "a1")
    assert record["state"] == "active"

    # Force clear
    result = am.force_clear(inst, "a1")
    assert result is True

    record = store.load_alarm("test-world", "s01", "a1")
    assert record["state"] == "inactive"
    assert record["cleared_at"] is not None

    # Second clear should return False
    result = am.force_clear(inst, "a1")
    assert result is False


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
