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
    assert state.triggered_at == "2026-01-01T00:00:00Z"


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
    assert state.triggered_at != "2026-01-01T00:00:00Z"


def test_silence_interval_blocks_retrigger():
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    config = {"severity": "warning", "silenceInterval": 60}

    am._on_trigger(inst, "a1", config)
    state = am._get_state(inst, "a1")
    assert state.state == "active"
    assert state.trigger_count == 1
    assert state.silence_expires_at is not None

    # Second trigger during silence - should be ignored
    am._on_trigger(inst, "a1", config)
    assert state.trigger_count == 1  # unchanged


def test_silence_expired_allows_retrigger(monkeypatch):
    from datetime import datetime, timezone, timedelta
    import src.runtime.alarm_manager as alarm_module
    am = AlarmManager(None, None, None)
    inst = FakeInstance()
    config = {"severity": "warning", "silenceInterval": 60}

    am._on_trigger(inst, "a1", config)
    state = am._get_state(inst, "a1")
    assert state.trigger_count == 1
    assert state.silence_expires_at is not None

    future = datetime.now(timezone.utc) + timedelta(seconds=120)
    FakeDatetime = type("FakeDatetime", (datetime,), {"now": lambda tz=None: future})
    monkeypatch.setattr(alarm_module, "datetime", FakeDatetime)

    am._on_trigger(inst, "a1", config)
    assert state.trigger_count == 2


class FakeInstanceWithProps:
    def __init__(self):
        self.instance_id = "inst-01"
        self.world_id = "demo-world"
        self.id = "inst-01"
        self.variables = {"temperature": 85.0, "threshold": 80.0}
        self.attributes = {"unit": "celsius"}
        self.state = {"current": "monitoring"}


def test_interpolate_message():
    am = AlarmManager(None, None, None)
    inst = FakeInstanceWithProps()
    msg = am._interpolate_message("Temp {temperature} exceeds {threshold}", inst)
    assert msg == "Temp 85.0 exceeds 80.0"


def test_interpolate_message_fallback():
    am = AlarmManager(None, None, None)
    inst = FakeInstanceWithProps()
    msg = am._interpolate_message("Unknown {missing} here", inst)
    assert msg == "Unknown {missing} here"


def test_publish_alarm_triggered_event():
    events = []

    class FakeBus:
        def publish(self, event_type, payload, source=None, scope=None, target=None):
            events.append((event_type, payload))

    am = AlarmManager(None, FakeBus(), None)
    inst = FakeInstanceWithProps()
    config = {
        "category": "temp",
        "title": "Overheat",
        "severity": "warning",
        "level": 1,
        "triggerMessage": "Hot {temperature}",
    }
    am._on_trigger(inst, "a1", config)
    assert len(events) == 1
    etype, payload = events[0]
    assert etype == "alarmTriggered"
    assert payload["alarmId"] == "a1"
    assert payload["severity"] == "warning"
    assert "Hot 85.0" in payload["message"]
    assert payload["triggerCount"] == 1
    assert payload["repeated"] is False


def test_publish_alarm_triggered_repeated_event():
    events = []

    class FakeBus:
        def publish(self, event_type, payload, source=None, scope=None, target=None):
            events.append((event_type, payload))

    am = AlarmManager(None, FakeBus(), None)
    inst = FakeInstanceWithProps()
    config = {
        "category": "temp",
        "title": "Overheat",
        "severity": "warning",
        "level": 1,
        "triggerMessage": "Hot {temperature}",
    }
    am._on_trigger(inst, "a1", config)
    assert len(events) == 1
    assert events[0][1]["repeated"] is False

    am._on_trigger(inst, "a1", config)
    assert len(events) == 2
    etype, payload = events[1]
    assert etype == "alarmTriggered"
    assert payload["triggerCount"] == 2
    assert payload["repeated"] is True


def test_publish_alarm_cleared_event():
    events = []

    class FakeBus:
        def publish(self, event_type, payload, source=None, scope=None, target=None):
            events.append((event_type, payload))

    am = AlarmManager(None, FakeBus(), None)
    inst = FakeInstanceWithProps()
    config = {
        "category": "temp",
        "title": "Overheat",
        "severity": "warning",
        "level": 1,
        "triggerMessage": "Hot {temperature}",
        "clearMessage": "Cooled {temperature}",
    }
    am._on_trigger(inst, "a1", config)
    assert len(events) == 1

    am._on_clear(inst, "a1", config)
    assert len(events) == 2
    etype, payload = events[1]
    assert etype == "alarmCleared"
    assert payload["alarmId"] == "a1"
    assert "Cooled 85.0" in payload["message"]
    assert payload["timestamp"] is not None
