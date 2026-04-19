import pytest
from src.runtime.event_bus import EventBusRegistry
from src.runtime.trigger_registry import TriggerRegistry
from src.runtime.triggers.event_trigger import EventTrigger
from src.runtime.triggers.value_changed_trigger import ValueChangedTrigger
from src.runtime.instance_manager import InstanceManager


def test_event_drives_state_transition():
    """Event 'start' triggers behavior with transition action, changing state from idle to monitoring."""
    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    te.add_trigger(ValueChangedTrigger())

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


def test_state_enter_triggers_value_changed_behavior():
    """When state changes to monitoring, valueChanged trigger on state.current fires."""
    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    te.add_trigger(ValueChangedTrigger())

    mgr = InstanceManager(bus_reg, trigger_registry=te)
    inst = mgr.create(
        world_id="w1",
        model_name="sensor",
        instance_id="s1",
        scope="world",
        state={"current": "idle", "enteredAt": None},
        variables={"log": ""},
        model={
            "transitions": {
                "startMonitoring": {"from": "idle", "to": "monitoring"}
            },
            "behaviors": {
                "onStart": {
                    "trigger": {"type": "event", "name": "start"},
                    "actions": [{"type": "transition", "transition": "startMonitoring"}],
                },
                "onEnterMonitoring": {
                    "trigger": {"type": "valueChanged", "name": "state.current", "value": "monitoring"},
                    "actions": [{
                        "type": "runScript",
                        "scriptEngine": "python",
                        "script": "this.variables.log = 'entered monitoring'",
                    }],
                }
            }
        },
    )

    bus = bus_reg.get_or_create("w1")
    bus.publish("start", {}, source="ext", scope="world")

    assert inst.state["current"] == "monitoring"
    assert inst.variables["log"] == "entered monitoring"


def test_run_script_triggers_value_changed():
    """Script that changes a variable triggers valueChanged behavior."""
    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    te.add_trigger(ValueChangedTrigger())

    mgr = InstanceManager(bus_reg, trigger_registry=te)
    inst = mgr.create(
        world_id="w1",
        model_name="sensor",
        instance_id="s1",
        scope="world",
        variables={"temperature": 20, "alert": False},
        model={
            "behaviors": {
                "onHeat": {
                    "trigger": {"type": "event", "name": "heat"},
                    "actions": [{
                        "type": "runScript",
                        "scriptEngine": "python",
                        "script": "this.variables.temperature = 80",
                    }],
                },
                "onTempHigh": {
                    "trigger": {"type": "valueChanged", "name": "variables.temperature", "value": 80},
                    "actions": [{
                        "type": "runScript",
                        "scriptEngine": "python",
                        "script": "this.variables.alert = True",
                    }],
                }
            }
        },
    )

    bus = bus_reg.get_or_create("w1")
    bus.publish("heat", {}, source="ext", scope="world")

    assert inst.variables["temperature"] == 80
    assert inst.variables["alert"] is True


def test_full_state_machine_lifecycle():
    """idle -(start)-> monitoring -(stop)-> idle"""
    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    te.add_trigger(ValueChangedTrigger())

    mgr = InstanceManager(bus_reg, trigger_registry=te)
    inst = mgr.create(
        world_id="w1",
        model_name="sensor",
        instance_id="s1",
        scope="world",
        state={"current": "idle", "enteredAt": None},
        variables={"temperature": 25, "alertCount": 0},
        model={
            "transitions": {
                "startMonitoring": {"from": "idle", "to": "monitoring"},
                "stopMonitoring": {"from": "monitoring", "to": "idle"},
            },
            "behaviors": {
                "onStart": {
                    "trigger": {"type": "event", "name": "start"},
                    "actions": [{"type": "transition", "transition": "startMonitoring"}],
                },
                "onStop": {
                    "trigger": {"type": "event", "name": "stop"},
                    "actions": [{"type": "transition", "transition": "stopMonitoring"}],
                },
                "onEnterMonitoring": {
                    "trigger": {"type": "valueChanged", "name": "state.current", "value": "monitoring"},
                    "actions": [{
                        "type": "runScript",
                        "scriptEngine": "python",
                        "script": "this.variables.alertCount = 0",
                    }],
                },
            }
        },
    )

    bus = bus_reg.get_or_create("w1")

    # Start monitoring
    bus.publish("start", {}, source="ext", scope="world")
    assert inst.state["current"] == "monitoring"
    assert inst.variables["alertCount"] == 0

    # Stop monitoring
    bus.publish("stop", {}, source="ext", scope="world")
    assert inst.state["current"] == "idle"
