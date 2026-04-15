import pytest
from src.runtime.state_manager import StateManager
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry


class FakeEventLogStore:
    def __init__(self):
        self.events = []

    def append(self, project_id, event_id, event_type, payload, source, scope):
        self.events.append({
            "project_id": project_id,
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "source": source,
            "scope": scope,
            "timestamp": "2024-01-01T00:00:00+00:00",
        })

    def replay_after(self, project_id, last_event_id):
        result = []
        for evt in self.events:
            if evt["project_id"] != project_id:
                continue
            if last_event_id is None:
                result.append(evt)
            elif evt["event_id"] > last_event_id:
                result.append(evt)
        return result


class FakeInstanceStore:
    def __init__(self):
        self.instances = {}
        self.project_states = {}

    def save_instance(self, project_id, instance_id, scope, snapshot):
        self.instances[(project_id, instance_id, scope)] = snapshot

    def load_instance(self, project_id, instance_id, scope):
        snap = self.instances.get((project_id, instance_id, scope))
        if snap is None:
            return None
        snap_copy = dict(snap)
        snap_copy["project_id"] = project_id
        snap_copy["instance_id"] = instance_id
        snap_copy["scope"] = scope
        return snap_copy

    def list_instances(self, project_id, scope=None, lifecycle_state=None):
        result = []
        for (pid, iid, sc), snap in self.instances.items():
            if pid != project_id:
                continue
            if scope is not None and sc != scope:
                continue
            if lifecycle_state is not None and snap.get("lifecycle_state") != lifecycle_state:
                continue
            snap_copy = dict(snap)
            snap_copy["project_id"] = pid
            snap_copy["instance_id"] = iid
            snap_copy["scope"] = sc
            result.append(snap_copy)
        return result

    def delete_instance(self, project_id, instance_id, scope):
        key = (project_id, instance_id, scope)
        if key in self.instances:
            del self.instances[key]
            return True
        return False

    def save_project_state(self, project_id, last_event_id, checkpointed_at):
        self.project_states[project_id] = {
            "last_event_id": last_event_id,
            "checkpointed_at": checkpointed_at,
        }

    def load_project_state(self, project_id):
        return self.project_states.get(project_id)


class FakeSceneStore:
    def __init__(self):
        self.scenes = {}

    def save_scene(self, project_id, scene_id, scene_data):
        self.scenes[(project_id, scene_id)] = scene_data

    def load_scene(self, project_id, scene_id):
        return self.scenes.get((project_id, scene_id))

    def list_scenes(self, project_id):
        return [
            dict(data, project_id=pid, scene_id=sid)
            for (pid, sid), data in self.scenes.items()
            if pid == project_id
        ]

    def delete_scene(self, project_id, scene_id):
        key = (project_id, scene_id)
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


def test_checkpoint_project_saves_instances_and_state(state_mgr):
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg, instance_store=state_mgr._instance_store)
    sm = StateManager(im, None, state_mgr._instance_store, state_mgr._scene_store, state_mgr._event_log_store)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    sm.checkpoint_project("proj-01", last_event_id="evt-5")
    assert ("proj-01", "ladle-001", "project") in state_mgr._instance_store.instances
    assert state_mgr._instance_store.project_states["proj-01"]["last_event_id"] == "evt-5"
    sm.shutdown()


def test_restore_project_hydrates_instances_and_replays_events(state_mgr):
    bus_reg = EventBusRegistry()
    store = FakeInstanceStore()
    store.instances[("proj-01", "ladle-001", "project")] = {
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
    store.project_states["proj-01"] = {"last_event_id": "evt-1", "checkpointed_at": "2024-01-01T00:00:00+00:00"}
    im = InstanceManager(bus_reg, instance_store=store)
    event_store = FakeEventLogStore()
    event_store.events.append({
        "project_id": "proj-01",
        "event_id": "evt-2",
        "event_type": "ladleLoaded",
        "payload": {"amount": 100},
        "source": "src-1",
        "scope": "project",
        "timestamp": "2024-01-01T00:01:00+00:00",
    })
    sm = StateManager(im, None, store, state_mgr._scene_store, event_store)
    sm.restore_project("proj-01")
    inst = im.get("proj-01", "ladle-001", scope="project")
    assert inst is not None
    assert inst.model_name == "ladle"
    sm.shutdown()


def test_checkpoint_scene_saves_scene_and_instances(state_mgr):
    from src.runtime.scene_manager import SceneManager
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg, instance_store=state_mgr._instance_store)
    scene_mgr = SceneManager(im, bus_reg)
    sm = StateManager(im, scene_mgr, state_mgr._instance_store, state_mgr._scene_store, state_mgr._event_log_store)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    scene_mgr.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    sm.checkpoint_scene("proj-01", "drill", last_event_id="evt-10")
    assert ("proj-01", "drill") in state_mgr._scene_store.scenes
    assert state_mgr._scene_store.scenes[("proj-01", "drill")]["last_event_id"] == "evt-10"
    # scene-scoped instance should be saved
    assert ("proj-01", "ladle-001", "scene:drill") in state_mgr._instance_store.instances
    sm.shutdown()


def test_restore_scene_hydrates_scene_and_instances(state_mgr):
    from src.runtime.scene_manager import SceneManager
    bus_reg = EventBusRegistry()
    store = FakeInstanceStore()
    store.instances[("proj-01", "ladle-001", "scene:drill")] = {
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
    scene_store.scenes[("proj-01", "drill")] = {
        "mode": "isolated",
        "refs": ["ladle-001"],
        "local_instances": {},
    }
    im = InstanceManager(bus_reg, instance_store=store)
    scene_mgr = SceneManager(im, bus_reg)
    sm = StateManager(im, scene_mgr, store, scene_store, state_mgr._event_log_store)
    scene = sm.restore_scene("proj-01", "drill")
    assert scene is not None
    assert scene["mode"] == "isolated"
    inst = im.get("proj-01", "ladle-001", scope="scene:drill")
    assert inst is not None
    assert inst.variables["steelAmount"] == 180
    sm.shutdown()


def test_track_and_untrack_project(state_mgr):
    state_mgr.track_project("proj-a")
    assert "proj-a" in state_mgr._loaded_projects
    state_mgr.untrack_project("proj-a")
    assert "proj-a" not in state_mgr._loaded_projects
