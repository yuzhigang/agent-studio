import pytest
from src.runtime.alarm_manager import AlarmManager, AlarmState


class FakeInstance:
    def __init__(self):
        self.instance_id = "inst-01"
        self.world_id = "demo-world"
        self.id = "inst-01"


def test_alarm_state_dataclass():
    state = AlarmState(alarm_id="a1", instance_id="inst-01", world_id="demo-world")
    assert state.state == "inactive"
    assert state.triggered_at is None
    assert state.cleared_at is None
    assert state.trigger_count == 0
    assert state.silence_expires_at is None


def test_alarm_manager_init():
    am = AlarmManager(trigger_registry=None, event_bus=None, store=None)
    assert am is not None


def test_build_default_clear_for_condition():
    am = AlarmManager(None, None, None)
    trigger = {"type": "condition", "condition": "this.variables.temperature > 80"}
    clear = am._build_default_clear(trigger)
    assert clear["type"] == "condition"
    assert clear["condition"] == "not (this.variables.temperature > 80)"


def test_build_default_clear_for_event_is_none():
    am = AlarmManager(None, None, None)
    trigger = {"type": "event", "name": "start"}
    assert am._build_default_clear(trigger) is None


class FakeTriggerRegistry:
    def __init__(self):
        self._entries = []

    def register(self, instance, trigger, callback, tag=None):
        entry_id = f"entry_{len(self._entries)}"
        self._entries.append({"id": entry_id, "instance": instance, "trigger": trigger, "tag": tag})
        return entry_id

    def unregister(self, entry_id):
        self._entries = [e for e in self._entries if e["id"] != entry_id]


def test_register_instance_alarms():
    fake_reg = FakeTriggerRegistry()
    am = AlarmManager(fake_reg, None, None)
    inst = FakeInstance()

    configs = {
        "alarm1": {
            "trigger": {"type": "event", "name": "start"},
            "clear": {"type": "event", "name": "stop"},
        }
    }
    am.register_instance_alarms(inst, configs)
    assert len(fake_reg._entries) == 2
    assert fake_reg._entries[0]["tag"] == "alarm:alarm1:trigger"
    assert fake_reg._entries[1]["tag"] == "alarm:alarm1:clear"


def test_unregister_instance_alarms():
    fake_reg = FakeTriggerRegistry()
    am = AlarmManager(fake_reg, None, None)
    inst = FakeInstance()

    configs = {"alarm1": {"trigger": {"type": "event", "name": "start"}}}
    am.register_instance_alarms(inst, configs)
    assert len(fake_reg._entries) == 1

    am.unregister_instance_alarms(inst)
    assert len(fake_reg._entries) == 0
    assert len(am._states) == 0


def test_on_trigger_inactive_to_active():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    am._states[("demo-world", "inst-01", "a1")] = AlarmState(
        alarm_id="a1", instance_id="inst-01", world_id="demo-world", state="inactive"
    )
    am._on_trigger(inst, "a1", {"severity": "warning", "triggerMessage": "hot"})
    state = am._states[("demo-world", "inst-01", "a1")]
    assert state.state == "active"
    assert state.triggered_at is not None
    assert state.trigger_count == 1


def test_on_clear_active_to_inactive():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    am._states[("demo-world", "inst-01", "a1")] = AlarmState(
        alarm_id="a1", instance_id="inst-01", world_id="demo-world",
        state="active", triggered_at="2026-01-01T00:00:00Z"
    )
    am._on_clear(inst, "a1", {"severity": "warning", "clearMessage": "ok"})
    state = am._states[("demo-world", "inst-01", "a1")]
    assert state.state == "inactive"
    assert state.cleared_at is not None


def test_on_trigger_already_active_increments_count():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    am._states[("demo-world", "inst-01", "a1")] = AlarmState(
        alarm_id="a1", instance_id="inst-01", world_id="demo-world",
        state="active", triggered_at="2026-01-01T00:00:00Z", trigger_count=1
    )
    am._on_trigger(inst, "a1", {"severity": "warning"})
    state = am._states[("demo-world", "inst-01", "a1")]
    assert state.state == "active"
    assert state.trigger_count == 2
