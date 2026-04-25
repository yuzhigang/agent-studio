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
                "agent_namespace": None,
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
    mgr = InstanceManager(
        instance_store=store,
        agent_namespace_resolver=lambda model_name: "logistics.ladle" if model_name == "ladle" else None,
    )
    inst = mgr.get("world-01", "ladle-001", scope="world")
    assert inst is not None
    assert inst.model_name == "ladle"
    assert inst._agent_namespace == "logistics.ladle"
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
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    mgr = InstanceManager(bus_reg, trigger_registry=te)
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
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    mgr = InstanceManager(bus_reg, trigger_registry=te)
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
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    mgr = InstanceManager(bus_reg, trigger_registry=te)
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


def test_on_event_trigger_event_action_external_publish():
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    class FakeEmitter:
        def __init__(self):
            self.external = []

        def publish_from_instance(self, **kwargs):
            raise AssertionError("internal emitter path should not be used for external triggerEvent")

        def publish_external(
            self,
            *,
            event_type,
            payload,
            scope="world",
            target=None,
            trace_id=None,
            headers=None,
        ):
            self.external.append(
                {
                    "event_type": event_type,
                    "payload": payload,
                    "scope": scope,
                    "target": target,
                    "trace_id": trace_id,
                    "headers": headers,
                }
            )
            return "msg-1"

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    emitter = FakeEmitter()
    mgr = InstanceManager(bus_reg, world_event_emitter=emitter, trigger_registry=te)
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
                            "external": True,
                            "headers": {"priority": "high"},
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
    assert received == []
    assert emitter.external == [
        {
            "event_type": "ladleLoaded",
            "payload": {"ladleId": "ladle-001", "steelAmount": 180},
            "scope": "world",
            "target": None,
            "trace_id": None,
            "headers": {"priority": "high"},
        }
    ]


def test_on_event_trigger_event_action_external_writes_outbox(tmp_path):
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger
    from src.runtime.messaging import MessageHub, WorldMessageSender
    from src.runtime.messaging.sqlite_store import SQLiteMessageStore
    from src.runtime.world_event_emitter import WorldEventEmitter

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    store = SQLiteMessageStore(str(tmp_path / "messagebox"))
    hub = MessageHub(message_store=store, channel=None, poll_interval=0.01)
    sender = WorldMessageSender(world_id="world-01", hub=hub, source="world:world-01")
    mgr = InstanceManager(bus_reg, world_event_emitter=None, trigger_registry=te)
    emitter = WorldEventEmitter(bus_reg.get_or_create("world-01"), mgr, sender)
    mgr.bind_world_event_emitter(emitter)

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
                            "external": True,
                            "headers": {"priority": "high"},
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
    bus.publish("beginLoad", {}, source="external", scope="world")

    pending = store.outbox_read_pending(limit=10)
    store.close()

    assert len(pending) == 1
    assert pending[0].source_world == "world-01"
    assert pending[0].target_world is None
    assert pending[0].event_type == "ladleLoaded"
    assert pending[0].payload == {"ladleId": "ladle-001", "steelAmount": 180}
    assert pending[0].source == "world:world-01"


@pytest.mark.parametrize(
    ("action_patch", "message"),
    [
        ({"targetWorldId": "factory-b"}, "does not support targetWorldId"),
        ({"scope": "scene:"}, "scope must be 'world' or 'scene:<scene_id>'"),
        ({"target": 123}, "target must be a string"),
        ({"traceId": 123}, "traceId must be a string"),
        ({"headers": {"priority": 1}}, "headers must be a dict"),
        ({"headers": "priority=high"}, "headers must be a dict"),
    ],
)
def test_external_trigger_event_validates_new_contract(action_patch, message):
    class FakeEmitter:
        def publish_external(self, **kwargs):
            raise AssertionError("publish_external should not be called when validation fails")

    mgr = InstanceManager(EventBusRegistry(), world_event_emitter=FakeEmitter())
    inst = mgr.create(
        world_id="world-a",
        model_name="ladle",
        instance_id="ladle-001",
        scope="scene:scene-a",
        model={},
    )

    action = {
        "type": "triggerEvent",
        "name": "ladle.loaded",
        "external": True,
        "scope": "scene:scene-a",
        "target": "ladle-002",
        "payload": {"ladleId": "this.id"},
        "headers": {"priority": "high"},
    }
    action.update(action_patch)

    with pytest.raises(ValueError, match=message):
        mgr._execute_action(inst, action, {}, "external")


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


def test_create_updates_snapshot():
    mgr = InstanceManager()
    inst = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert inst.snapshot["temperature"] == 1500
    assert inst.world_state["id"] == "ladle-001"
    assert inst.world_state["state"] == "idle"
    assert inst.world_state["snapshot"]["temperature"] == 1500


def test_run_script_updates_snapshot():
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))
    mgr = InstanceManager(bus_reg, trigger_registry=te)
    inst = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}},
            "behaviors": {
                "updateTemp": {
                    "trigger": {"type": "event", "name": "heat"},
                    "actions": [
                        {
                            "type": "runScript",
                            "scriptEngine": "python",
                            "script": "this.variables.temperature = 1600",
                        }
                    ],
                }
            },
        },
    )
    bus = bus_reg.get_or_create("proj-01")
    bus.publish("heat", {}, source="external", scope="world")
    assert inst.snapshot["temperature"] == 1600
    assert inst.world_state["snapshot"]["temperature"] == 1600


def test_transition_lifecycle_archived_clears_snapshot():
    mgr = InstanceManager()
    inst = mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    assert inst.snapshot["temperature"] == 1500
    mgr.transition_lifecycle("proj-01", "ladle-001", "archived")
    assert inst.snapshot == {}
    assert inst._audit_fields == {}


def test_behavior_context_includes_world_state():
    from src.runtime.world_state import WorldState

    mgr = InstanceManager()
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    ws = WorldState(mgr, "proj-01")
    mgr._world_state = ws

    inst = mgr.get("proj-01", "ladle-001")
    ctx = mgr._build_behavior_context(inst, {"foo": "bar"}, "external")
    assert "world_state" in ctx
    assert "ladle" in ctx["world_state"]
    assert ctx["world_state"]["ladle"][0]["snapshot"]["temperature"] == 1500


def test_build_persist_dict_includes_world_state():
    class FakeStore:
        def __init__(self):
            self.saved = {}
        def save_instance(self, world_id, instance_id, scope, snapshot):
            self.saved[(world_id, instance_id, scope)] = snapshot

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    mgr.create(
        world_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    snap = store.saved[("proj-01", "ladle-001", "world")]
    assert "world_state" in snap
    assert snap["world_state"]["id"] == "ladle-001"
    assert snap["world_state"]["snapshot"]["temperature"] == 1500


def test_lazy_load_restores_world_state():
    class FakeStore:
        def load_instance(self, world_id, instance_id, scope):
            return {
                "world_id": world_id,
                "instance_id": instance_id,
                "scope": scope,
                "model_name": "ladle",
                "model_version": "1.0",
                "attributes": {},
                "state": {"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
                "variables": {"temperature": 1500},
                "links": {},
                "memory": {},
                "audit": {"version": 1},
                "lifecycle_state": "active",
                "world_state": {
                    "id": instance_id,
                    "state": "idle",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "lifecycle_state": "active",
                    "snapshot": {"temperature": 1500},
                },
                "updated_at": "2024-01-01T00:00:00+00:00",
            }

    store = FakeStore()
    mgr = InstanceManager(instance_store=store)
    inst = mgr.get("proj-01", "ladle-001", scope="world")
    assert inst is not None
    assert inst.world_state["id"] == "ladle-001"
    assert inst.world_state["snapshot"]["temperature"] == 1500


def test_dict_proxy_tracks_changes():
    from src.runtime.instance_manager import _DictProxy

    data = {"temperature": 20, "nested": {"value": 1}}
    proxy = _DictProxy(data)
    proxy._changed_fields = []

    proxy.temperature = 25
    assert "temperature" in proxy._changed_fields

    proxy.nested.value = 2
    assert "nested.value" in proxy._changed_fields


def test_dict_proxy_tracks_with_path_prefix():
    from src.runtime.instance_manager import _DictProxy

    data = {"temperature": 20}
    proxy = _DictProxy(data, path_prefix="variables")
    proxy._changed_fields = []

    proxy.temperature = 25
    assert "variables.temperature" in proxy._changed_fields


def test_transition_state_changes_current_state():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="w1",
        model_name="ladle",
        instance_id="l1",
        scope="world",
        state={"current": "idle", "enteredAt": None},
        model={
            "transitions": {
                "start": {"from": "idle", "to": "monitoring"}
            }
        },
    )
    mgr._transition_state(inst, "start")
    assert inst.state["current"] == "monitoring"
    assert inst.state["enteredAt"] is not None


def test_transition_state_from_wrong_state_skips():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="w1",
        model_name="ladle",
        instance_id="l1",
        scope="world",
        state={"current": "alert", "enteredAt": None},
        model={
            "transitions": {
                "start": {"from": "idle", "to": "monitoring"}
            }
        },
    )
    mgr._transition_state(inst, "start")  # silent skip
    assert inst.state["current"] == "alert"


def test_execute_actions_runs_multiple_actions():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="w1",
        model_name="ladle",
        instance_id="l1",
        scope="world",
        variables={"count": 0, "temp": 20},
        model={
            "transitions": {
                "start": {"from": "idle", "to": "monitoring"}
            }
        },
    )
    actions = [
        {"type": "runScript", "scriptEngine": "python", "script": "this.variables.count += 1"},
        {"type": "runScript", "scriptEngine": "python", "script": "this.variables.temp = 30"},
    ]
    mgr._execute_actions(inst, actions, {}, "test")
    assert inst.variables["count"] == 1
    assert inst.variables["temp"] == 30


def test_execute_actions_transition_action():
    bus_reg = EventBusRegistry()
    mgr = InstanceManager(bus_reg)
    inst = mgr.create(
        world_id="w1",
        model_name="ladle",
        instance_id="l1",
        scope="world",
        state={"current": "idle", "enteredAt": None},
        model={
            "transitions": {
                "start": {"from": "idle", "to": "monitoring"}
            }
        },
    )
    actions = [
        {"type": "transition", "transition": "start"},
    ]
    mgr._execute_actions(inst, actions, {}, "test")
    assert inst.state["current"] == "monitoring"


def test_register_instance_creates_trigger_registry_entries():
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))

    mgr = InstanceManager(bus_reg, trigger_registry=te)

    inst = mgr.create(
        world_id="w1",
        model_name="ladle",
        instance_id="l1",
        scope="world",
        model={
            "behaviors": {
                "onStart": {
                    "trigger": {"type": "event", "name": "start"},
                    "actions": [{"type": "runScript", "scriptEngine": "python", "script": "this.variables.x = 1"}],
                }
            }
        },
    )

    bus = bus_reg.get_or_create("w1")
    bus.publish("start", {}, source="ext", scope="world")
    assert inst.variables["x"] == 1


def test_unregister_instance_removes_trigger_entries():
    from src.runtime.trigger_registry import TriggerRegistry
    from src.runtime.triggers.event_trigger import EventTrigger

    bus_reg = EventBusRegistry()
    te = TriggerRegistry()
    te.add_trigger(EventTrigger(bus_reg))

    mgr = InstanceManager(bus_reg, trigger_registry=te)

    mgr.create(
        world_id="w1",
        model_name="ladle",
        instance_id="l1",
        scope="world",
        model={
            "behaviors": {
                "onStart": {
                    "trigger": {"type": "event", "name": "start"},
                    "actions": [{"type": "runScript", "scriptEngine": "python", "script": "this.variables.x = 1"}],
                }
            }
        },
    )
    mgr.remove("w1", "l1", scope="world")

    bus = bus_reg.get_or_create("w1")
    received = []
    bus.register("observer", "world", "start", lambda t, p, s: received.append(t))
    bus.publish("start", {}, source="ext", scope="world")
    assert len(received) == 1  # only observer, not the removed instance
