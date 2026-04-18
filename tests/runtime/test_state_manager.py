import pytest
from src.runtime.state_manager import StateManager
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry


class FakeEventLogStore:
    def __init__(self):
        self.events = []

    def append(self, world_id, event_id, event_type, payload, source, scope):
        self.events.append({
            "world_id": world_id,
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "source": source,
            "scope": scope,
            "timestamp": "2024-01-01T00:00:00+00:00",
        })

    def replay_after(self, world_id, last_event_id):
        result = []
        for evt in self.events:
            if evt["world_id"] != world_id:
                continue
            if last_event_id is None:
                result.append(evt)
            elif evt["event_id"] > last_event_id:
                result.append(evt)
        return result


class FakeInstanceStore:
    def __init__(self):
        self.instances = {}
        self.world_states = {}

    def save_instance(self, world_id, instance_id, scope, snapshot):
        self.instances[(world_id, instance_id, scope)] = snapshot

    def load_instance(self, world_id, instance_id, scope):
        snap = self.instances.get((world_id, instance_id, scope))
        if snap is None:
            return None
        snap_copy = dict(snap)
        snap_copy["world_id"] = world_id
        snap_copy["instance_id"] = instance_id
        snap_copy["scope"] = scope
        return snap_copy

    def list_instances(self, world_id, scope=None, lifecycle_state=None):
        result = []
        for (pid, iid, sc), snap in self.instances.items():
            if pid != world_id:
                continue
            if scope is not None and sc != scope:
                continue
            if lifecycle_state is not None and snap.get("lifecycle_state") != lifecycle_state:
                continue
            snap_copy = dict(snap)
            snap_copy["world_id"] = pid
            snap_copy["instance_id"] = iid
            snap_copy["scope"] = sc
            result.append(snap_copy)
        return result

    def delete_instance(self, world_id, instance_id, scope):
        key = (world_id, instance_id, scope)
        if key in self.instances:
            del self.instances[key]
            return True
        return False

    def save_world_state(self, world_id, last_event_id, checkpointed_at):
        self.world_states[world_id] = {
            "last_event_id": last_event_id,
            "checkpointed_at": checkpointed_at,
        }

    def load_world_state(self, world_id):
        return self.world_states.get(world_id)


class FakeSceneStore:
    def __init__(self):
        self.scenes = {}

    def save_scene(self, world_id, scene_id, scene_data):
        self.scenes[(world_id, scene_id)] = scene_data

    def load_scene(self, world_id, scene_id):
        return self.scenes.get((world_id, scene_id))

    def list_scenes(self, world_id):
        return [
            dict(data, world_id=pid, scene_id=sid)
            for (pid, sid), data in self.scenes.items()
            if pid == world_id
        ]

    def delete_scene(self, world_id, scene_id):
        key = (world_id, scene_id)
        if key in self.scenes:
            del self.scenes[key]
            return True
        return False


@pytest.fixture
def state_mgr():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    store = FakeInstanceStore()
    scene_store = FakeSceneStore()
    event_store = FakeEventLogStore()
    sm = StateManager(im, None, store, scene_store, event_store)
    yield sm
    sm.shutdown()


def test_checkpoint_world_saves_instances_and_state(state_mgr):
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg, instance_store=state_mgr._instance_store)
    sm = StateManager(im, None, state_mgr._instance_store, state_mgr._scene_store, state_mgr._event_log_store)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    sm.checkpoint_world("world-01", last_event_id="evt-5")
    assert ("world-01", "ladle-001", "world") in state_mgr._instance_store.instances
    assert state_mgr._instance_store.world_states["world-01"]["last_event_id"] == "evt-5"
    sm.shutdown()


def test_restore_world_hydrates_instances_and_replays_events(state_mgr):
    bus_reg = EventBusRegistry()
    store = FakeInstanceStore()
    store.instances[("world-01", "ladle-001", "world")] = {
        "model_name": "ladle",
        "model_version": None,
        "attributes": {},
        "state": {},
        "variables": {},
        "links": {},
        "memory": {},
        "audit": {},
        "lifecycle_state": "active",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    store.world_states["world-01"] = {"last_event_id": "evt-1", "checkpointed_at": "2024-01-01T00:00:00+00:00"}
    im = InstanceManager(bus_reg, instance_store=store)
    event_store = FakeEventLogStore()
    event_store.events.append({
        "world_id": "world-01",
        "event_id": "evt-2",
        "event_type": "ladleLoaded",
        "payload": {"amount": 100},
        "source": "src-1",
        "scope": "world",
        "timestamp": "2024-01-01T00:01:00+00:00",
    })
    sm = StateManager(im, None, store, state_mgr._scene_store, event_store)
    sm.restore_world("world-01")
    inst = im.get("world-01", "ladle-001", scope="world")
    assert inst is not None
    assert inst.model_name == "ladle"
    sm.shutdown()


def test_checkpoint_scene_saves_scene_and_instances(state_mgr):
    from src.runtime.scene_manager import SceneManager
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg, instance_store=state_mgr._instance_store)
    scene_mgr = SceneManager(im, bus_reg)
    sm = StateManager(im, scene_mgr, state_mgr._instance_store, state_mgr._scene_store, state_mgr._event_log_store)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    scene_mgr.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    sm.checkpoint_scene("world-01", "drill", last_event_id="evt-10")
    assert ("world-01", "drill") in state_mgr._scene_store.scenes
    assert state_mgr._scene_store.scenes[("world-01", "drill")]["last_event_id"] == "evt-10"
    # scene-scoped instance should be saved
    assert ("world-01", "ladle-001", "scene:drill") in state_mgr._instance_store.instances
    sm.shutdown()


def test_restore_scene_hydrates_scene_and_instances(state_mgr):
    from src.runtime.scene_manager import SceneManager
    bus_reg = EventBusRegistry()
    store = FakeInstanceStore()
    store.instances[("world-01", "ladle-001", "scene:drill")] = {
        "model_name": "ladle",
        "model_version": None,
        "attributes": {},
        "state": {},
        "variables": {"steelAmount": 180},
        "links": {},
        "memory": {},
        "audit": {},
        "lifecycle_state": "active",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    scene_store = FakeSceneStore()
    scene_store.scenes[("world-01", "drill")] = {
        "mode": "isolated",
        "refs": ["ladle-001"],
        "local_instances": {},
    }
    im = InstanceManager(bus_reg, instance_store=store)
    scene_mgr = SceneManager(im, bus_reg)
    sm = StateManager(im, scene_mgr, store, scene_store, state_mgr._event_log_store)
    scene = sm.restore_scene("world-01", "drill")
    assert scene is not None
    assert scene["mode"] == "isolated"
    inst = im.get("world-01", "ladle-001", scope="scene:drill")
    assert inst is not None
    assert inst.variables["steelAmount"] == 180
    sm.shutdown()


def test_track_and_untrack_world(state_mgr):
    state_mgr.track_world("world-a")
    assert "world-a" in state_mgr._loaded_worlds
    state_mgr.untrack_world("world-a")
    assert "world-a" not in state_mgr._loaded_worlds
