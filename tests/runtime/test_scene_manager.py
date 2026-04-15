import pytest
from src.runtime.scene_manager import SceneManager
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry


def test_start_shared_scene_references_project_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneManager(im, bus_reg)
    scene = ctrl.start(
        project_id="proj-01",
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
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project", variables={"steelAmount": 180})
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    # Both project and scene copies exist; get isolates by scope
    assert im.get("proj-01", "ladle-001", scope="project").scope == "project"
    assert im.get("proj-01", "ladle-001", scope="scene:drill").scope == "scene:drill"
    proj_list = im.list_by_scope("proj-01", "project")
    scene_list = im.list_by_scope("proj-01", "scene:drill")
    assert len(proj_list) == 1
    assert len(scene_list) == 1
    assert proj_list[0].variables["steelAmount"] == 180
    assert scene_list[0].variables["steelAmount"] == 180


def test_isolated_scene_with_local_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneManager(im, bus_reg)
    scene = ctrl.start(
        project_id="proj-01",
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
    local = im.get("proj-01", "temp-inspector-01", scope="scene:drill")
    assert local is not None
    assert local.scope == "scene:drill"
    assert local.variables["targetLadle"] == "ladle-001"


def test_stop_scene_removes_local_and_cow_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    assert len(im.list_by_scope("proj-01", "scene:drill")) == 1
    assert ctrl.stop("proj-01", "drill") is True
    assert len(im.list_by_scope("proj-01", "scene:drill")) == 0
    assert ctrl.get("proj-01", "drill") is None


def test_isolated_scene_backfills_metrics():
    class FakeMetricStore:
        def latest(self, project_id, instance_id, metric_name):
            if metric_name == "temperature":
                return 1250.0
            return None

    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(
        project_id="proj-01",
        model_name="ladle",
        instance_id="ladle-001",
        scope="project",
        variables={"temperature": 25.0},
        model={
            "variables": {
                "temperature": {"x-category": "metric"},
                "steelAmount": {"x-category": "state"},
            }
        },
    )
    ctrl = SceneManager(im, bus_reg, metric_store=FakeMetricStore())
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    cow = im.get("proj-01", "ladle-001", scope="scene:drill")
    assert cow.variables["temperature"] == 1250.0
    # state variable should not be touched by metric backfill
    assert cow.variables.get("steelAmount", 0.0) == 0.0


def test_list_by_project():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(project_id="proj-01", scene_id="monitor", mode="shared")
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated")
    ctrl.start(project_id="proj-02", scene_id="cast", mode="shared")
    scenes = ctrl.list_by_project("proj-01")
    assert len(scenes) == 2
    assert {s["scene_id"] for s in scenes} == {"monitor", "drill"}


def test_start_persists_scene_to_store():
    class FakeStore:
        def __init__(self):
            self.saved = {}
        def save_scene(self, project_id, scene_id, scene_data):
            self.saved[(project_id, scene_id)] = scene_data

    store = FakeStore()
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneManager(im, bus_reg, scene_store=store)
    ctrl.start(project_id="proj-01", scene_id="monitor", mode="shared", references=["ladle-001"])
    assert ("proj-01", "monitor") in store.saved
    assert store.saved[("proj-01", "monitor")]["mode"] == "shared"
    assert store.saved[("proj-01", "monitor")]["refs"] == ["ladle-001"]


def test_stop_deletes_scene_from_store():
    class FakeStore:
        def __init__(self):
            self.saved = {}
            self.deleted = []
        def save_scene(self, project_id, scene_id, scene_data):
            self.saved[(project_id, scene_id)] = scene_data
        def delete_scene(self, project_id, scene_id):
            self.deleted.append((project_id, scene_id))

    store = FakeStore()
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(project_id="proj-01", model_name="ladle", instance_id="ladle-001", scope="project")
    ctrl = SceneManager(im, bus_reg, scene_store=store)
    ctrl.start(project_id="proj-01", scene_id="drill", mode="isolated", references=["ladle-001"])
    ctrl.stop("proj-01", "drill")
    assert ("proj-01", "drill") in store.deleted
