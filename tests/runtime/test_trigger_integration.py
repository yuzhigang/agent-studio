import pytest
from src.runtime.event_bus import EventBusRegistry
from src.runtime.trigger_registry import TriggerRegistry
from src.runtime.triggers.event_trigger import EventTrigger
from src.runtime.instance_manager import InstanceManager


def test_event_drives_state_transition():
    """Event 'start' triggers behavior with transition action, changing state from idle to monitoring."""
    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))

    mgr = InstanceManager(bus_reg, trigger_registry=te)
    inst = mgr.create(
        world_id="w1",
        model_name="sensor",
        instance_id="s1",
        scope="world",
        state={"current": "idle", "enteredAt": None},
        model={
            "transitions": {
                "startMonitoring": {"from": "idle", "to": "monitoring"}
            },
            "behaviors": {
                "onStart": {
                    "trigger": {"type": "event", "name": "start"},
                    "actions": [{"type": "transition", "transition": "startMonitoring"}],
                }
            }
        },
    )

    bus = bus_reg.get_or_create("w1")
    bus.publish("start", {}, source="ext", scope="world")

    assert inst.state["current"] == "monitoring"
