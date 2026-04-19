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
