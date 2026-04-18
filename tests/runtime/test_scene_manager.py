import pytest
from src.runtime.scene_manager import SceneManager
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry


def test_start_shared_scene_references_world_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl = SceneManager(im, bus_reg)
    scene = ctrl.start(
        world_id="world-01",
        scene_id="monitor",
        mode="shared",
        references=["ladle-001"],
    )
    assert scene["scene_id"] == "monitor"
    assert scene["mode"] == "shared"
    assert "ladle-001" in scene["references"]


def test_start_isolated_scene_creates_cow_copy():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world", variables={"steelAmount": 180})
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    # Both world and scene copies exist; get isolates by scope
    assert im.get("world-01", "ladle-001", scope="world").scope == "world"
    assert im.get("world-01", "ladle-001", scope="scene:drill").scope == "scene:drill"
    world_list = im.list_by_scope("world-01", "world")
    scene_list = im.list_by_scope("world-01", "scene:drill")
    assert len(world_list) == 1
    assert len(scene_list) == 1
    assert world_list[0].variables["steelAmount"] == 180
    assert scene_list[0].variables["steelAmount"] == 180


def test_isolated_scene_with_local_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl = SceneManager(im, bus_reg)
    scene = ctrl.start(
        world_id="world-01",
        scene_id="drill",
        mode="isolated",
        references=["ladle-001"],
        local_instances={
            "temp-inspector-01": {
                "modelName": "inspector",
                "variables": {"targetLadle": "ladle-001"},
            }
        },
    )
    local = im.get("world-01", "temp-inspector-01", scope="scene:drill")
    assert local is not None
    assert local.scope == "scene:drill"
    assert local.variables["targetLadle"] == "ladle-001"


def test_stop_scene_removes_local_and_cow_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    assert len(im.list_by_scope("world-01", "scene:drill")) == 1
    assert ctrl.stop("world-01", "drill") is True
    assert len(im.list_by_scope("world-01", "scene:drill")) == 0
    assert ctrl.get("world-01", "drill") is None


def test_isolated_scene_backfills_metrics():
    class FakeMetricStore:
        def latest(self, world_id, instance_id, metric_name):
            if metric_name == "temperature":
                return 1250.0
            return None

    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(
        world_id="world-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        variables={"temperature": 25.0},
        model={
            "variables": {
                "temperature": {"x-category": "metric"},
                "steelAmount": {"x-category": "state"},
            }
        },
    )
    ctrl = SceneManager(im, bus_reg, metric_store=FakeMetricStore())
    ctrl.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    cow = im.get("world-01", "ladle-001", scope="scene:drill")
    assert cow.variables["temperature"] == 1250.0
    # state variable should not be touched by metric backfill
    assert cow.variables.get("steelAmount", 0.0) == 0.0


def test_list_by_world():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(world_id="world-01", scene_id="monitor", mode="shared")
    ctrl.start(world_id="world-01", scene_id="drill", mode="isolated")
    ctrl.start(world_id="world-02", scene_id="cast", mode="shared")
    scenes = ctrl.list_by_world("world-01")
    assert len(scenes) == 2
    assert {s["scene_id"] for s in scenes} == {"monitor", "drill"}


def test_start_persists_scene_to_store():
    class FakeStore:
        def __init__(self):
            self.saved = {}
        def save_scene(self, world_id, scene_id, scene_data):
            self.saved[(world_id, scene_id)] = scene_data

    store = FakeStore()
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl = SceneManager(im, bus_reg, scene_store=store)
    ctrl.start(world_id="world-01", scene_id="monitor", mode="shared", references=["ladle-001"])
    assert ("world-01", "monitor") in store.saved
    assert store.saved[("world-01", "monitor")]["mode"] == "shared"
    assert store.saved[("world-01", "monitor")]["refs"] == ["ladle-001"]


def test_stop_deletes_scene_from_store():
    class FakeStore:
        def __init__(self):
            self.saved = {}
            self.deleted = []
        def save_scene(self, world_id, scene_id, scene_data):
            self.saved[(world_id, scene_id)] = scene_data
        def delete_scene(self, world_id, scene_id):
            self.deleted.append((world_id, scene_id))

    store = FakeStore()
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001", scope="world")
    ctrl = SceneManager(im, bus_reg, scene_store=store)
    ctrl.start(world_id="world-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    ctrl.stop("world-01", "drill")
    assert ("world-01", "drill") in store.deleted
