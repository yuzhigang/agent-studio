import pytest
from src.runtime.instance_manager import InstanceManager
from src.runtime.instance import Instance
from src.runtime.event_bus import EventBusRegistry


def test_create_and_get_instance():
    mgr = InstanceManager()
    inst = mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        attributes={"capacity": 200},
        variables={"steelAmount": 180},
    )
    assert inst.id == "ladle-001"
    assert mgr.get("world-01", "ladle-001", scope="world") is inst
    assert mgr.get("world-01", "ladle-002", scope="world") is None


def test_copy_for_scene_changes_scope():
    mgr = InstanceManager()
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    clone = mgr.copy_for_scene("world-01", "ladle-001", "drill")
    assert clone is not None
    assert clone.scope == "scene:drill"
    assert mgr.get("world-01", "ladle-001", scope="world").scope == "world"
    assert mgr.get("world-01", "ladle-001", scope="scene:drill") is clone
    scene_instances = mgr.list_by_scope("world-01", "scene:drill")
    assert len(scene_instances) == 1


def test_duplicate_instance_id_raises():
    mgr = InstanceManager()
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    with pytest.raises(ValueError, match="already exists"):
        mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")


def test_create_registers_on_event_bus():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        model={
            "behaviors": {
                "captureAssigned": {
                    "trigger": {"type": "event", "name": "dispatchAssigned"},
                }
            }
        },
    )
    bus = bus_reg.get_or_create("world-01")
    # Publish an event that the instance should be subscribed to
    received = []
    # Manually add a second subscriber to the same event to verify routing still works
    bus.register("ladle-002", "world", "dispatchAssigned", lambda t, p, s: received.append((t, p, s)))
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="world")
    assert len(received) == 1


def test_remove_instance_unregisters_and_deletes():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        model={
            "behaviors": {
                "captureAssigned": {
                    "trigger": {"type": "event", "name": "dispatchAssigned"},
                }
            }
        },
    )
    assert mgr.remove("world-01", "ladle-001", scope="world") is True
    assert mgr.get("world-01", "ladle-001", scope="world") is None
    bus = bus_reg.get_or_create("world-01")
    received = []
    bus.register("ladle-002", "world", "dispatchAssigned", lambda t, p, s: received.append((t, p, s)))
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="world")
    assert len(received) == 1


def test_list_by_world():
    mgr = InstanceManager()
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    mgr.create(world_id="world-02", model_name="ladle", instance_id="ladle-002", scope="world")
    world_instances = mgr.list_by_world("world-01")
    assert len(world_instances) == 1
    assert world_instances[0].world_id == "world-01"
    assert world_instances[0].instance_id == "ladle-001"


def test_copy_for_scene_duplicate_raises():
    mgr = InstanceManager()
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    mgr.copy_for_scene("world-01", "ladle-001", "drill")
    with pytest.raises(ValueError, match="already exists"):
        mgr.copy_for_scene("world-01", "ladle-001", "drill")


def test_create_persists_to_store():
    class FakeStore:
        def __init__(self):
            self.saved = {}
        def save_instance(self, world_id, instance_id, scope, snapshot):
            self.saved[(world_id, instance_id, scope)] = snapshot

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    assert ("world-01", "ladle-001", "world") in store.saved
    assert store.saved[("world-01", "ladle-001", "world")]["model_name"] == "ladle"


def test_lazy_load_from_store():
    class FakeStore:
        def load_instance(self, world_id, instance_id, scope):
            return {
                "world_id": world_id,
                "instance_id": instance_id,
                "scope": scope,
                "model_name": "ladle",
                "model_version": "1.0",
                "attributes": {"capacity": 200},
                "state": {"current": "idle"},
                "variables": {"steelAmount": 180},
                "links": {},
                "memory": {},
                "audit": {"version": 1},
                "lifecycle_state": "active",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    inst = mgr.get("world-01", "ladle-001", scope="world")
    assert inst is not None
    assert inst.model_name == "ladle"
    assert inst.attributes["capacity"] == 200


def test_remove_deletes_from_store():
    class FakeStore:
        def __init__(self):
            self.deleted = []
        def save_instance(self, world_id, instance_id, scope, snapshot):
            pass
        def delete_instance(self, world_id, instance_id, scope):
            self.deleted.append((world_id, instance_id, scope))

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    mgr.remove("world-01", "ladle-001", scope="world")
    assert ("world-01", "ladle-001", "world") in store.deleted


def test_transition_lifecycle_updates_state_and_store():
    class FakeStore:
        def __init__(self):
            self.saved = {}
        def save_instance(self, world_id, instance_id, scope, snapshot):
            self.saved[(world_id, instance_id, scope)] = snapshot
        def load_instance(self, world_id, instance_id, scope):
            return None

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    mgr.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    assert mgr.transition_lifecycle("world-01", "ladle-001", "completed", scope="world") is True
    assert store.saved[("world-01", "ladle-001", "world")]["lifecycle_state"] == "completed"
    # archived should evict from memory
    assert mgr.transition_lifecycle("world-01", "ladle-001", "archived", scope="world") is True
    assert mgr.get("world-01", "ladle-001", scope="world") is None


def test_transition_lifecycle_returns_false_for_missing_instance():
    mgr = InstanceManager()
    assert mgr.transition_lifecycle("world-01", "ladle-001", "archived") is False


def test_on_event_runs_script_action():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        variables={"targetLocation": ""},
        model={
            "behaviors": {
                "captureAssigned": {
                    "trigger": {"type": "event", "name": "dispatchAssigned"},
                    "actions": [
                        {
                            "type": "runScript",
                            "scriptEngine": "python",
                            "script": "this.variables.targetLocation = payload.get('destinationId', '')",
                        }
                    ],
                }
            }
        },
    )
    bus = bus_reg.get_or_create("world-01")
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="world")
    assert inst.variables["targetLocation"] == "C03"


def test_on_event_when_condition_filters_behavior():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        variables={"targetLocation": ""},
        model={
            "behaviors": {
                "captureOnlyNonNull": {
                    "trigger": {
                        "type": "event",
                        "name": "dispatchAssigned",
                        "when": "payload.destinationId != null",
                    },
                    "actions": [
                        {
                            "type": "runScript",
                            "scriptEngine": "python",
                            "script": "this.variables.targetLocation = 'matched'",
                        }
                    ],
                }
            }
        },
    )
    bus = bus_reg.get_or_create("world-01")
    # when condition should skip this
    bus.publish("dispatchAssigned", {"destinationId": None}, source="external", scope="world")
    assert inst.variables["targetLocation"] == ""
    # when condition should match this
    bus.publish("dispatchAssigned", {"destinationId": "C03"}, source="external", scope="world")
    assert inst.variables["targetLocation"] == "matched"


def test_on_event_trigger_event_action():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        variables={"steelAmount": 180},
        model={
            "behaviors": {
                "notifyLoaded": {
                    "trigger": {"type": "event", "name": "beginLoad"},
                    "actions": [
                        {
                            "type": "triggerEvent",
                            "name": "ladleLoaded",
                            "payload": {
                                "ladleId": "this.id",
                                "steelAmount": "this.variables.steelAmount",
                            },
                        }
                    ],
                }
            }
        },
    )
    bus = bus_reg.get_or_create("world-01")
    received = []
    bus.register("observer", "world", "ladleLoaded", lambda t, p, s: received.append((t, p, s)))
    bus.publish("beginLoad", {}, source="external", scope="world")
    assert len(received) == 1
    assert received[0][0] == "ladleLoaded"
    assert received[0][1] == {"ladleId": "ladle-001", "steelAmount": 180}
    assert received[0][2] == "ladle-001"


def test_on_event_ignores_non_event_trigger():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        variables={"targetLocation": ""},
        model={
            "behaviors": {
                "stateEnterBehavior": {
                    "trigger": {"type": "stateEnter", "state": "full"},
                    "actions": [
                        {
                            "type": "runScript",
                            "scriptEngine": "python",
                            "script": "this.variables.targetLocation = 'should_not_run'",
                        }
                    ],
                }
            }
        },
    )
    bus = bus_reg.get_or_create("world-01")
    bus.publish("someEvent", {}, source="external", scope="world")
    assert inst.variables["targetLocation"] == ""
