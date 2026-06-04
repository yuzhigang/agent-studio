import pytest
import yaml
from pathlib import Path

from src.runtime.scene_manager import SceneManager
from src.runtime.instance_manager import InstanceManager
from src.runtime.event_bus import EventBusRegistry


class RecordingSceneStore:
    def __init__(self):
        self.saved = {}
        self.deleted = []

    def save_scene(self, world_id, scene_id, scene_data):
        self.saved[(world_id, scene_id)] = scene_data

    def load_scene(self, world_id, scene_id):
        return self.saved.get((world_id, scene_id))

    def list_scenes(self, world_id):
        return [
            dict(data, world_id=pid, scene_id=sid)
            for (pid, sid), data in self.saved.items()
            if pid == world_id
        ]

    def delete_scene(self, world_id, scene_id):
        self.deleted.append((world_id, scene_id))
        return self.saved.pop((world_id, scene_id), None) is not None


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


def test_stop_shared_scene_preserves_world_references_and_removes_local_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001")
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(
        world_id="world-01",
        scene_id="monitor",
        mode="shared",
        references=["ladle-001"],
        local_instances={"temp-inspector-01": {"modelName": "inspector"}},
    )

    assert ctrl.stop("world-01", "monitor") is True

    assert im.get("world-01", "ladle-001", scope="world") is not None
    assert im.list_by_scope("world-01", "scene:monitor") == []


def test_stop_keeps_scene_running_when_instance_cleanup_fails(monkeypatch):
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create(world_id="world-01", model_name="ladle", instance_id="ladle-001")
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(
        world_id="world-01",
        scene_id="drill",
        mode="isolated",
        references=["ladle-001"],
    )

    def fail_remove(*args, **kwargs):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(im, "remove", fail_remove)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        ctrl.stop("world-01", "drill")

    assert ctrl.get("world-01", "drill") is not None


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


def test_stop_preserves_scene_definition_in_store():
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
    assert ("world-01", "drill") in store.saved
    assert store.deleted == []


def test_start_rejects_legacy_local_instance_definition():
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg)

    with pytest.raises(ValueError, match="Invalid local instance definition"):
        ctrl.start(
            "world-01",
            "legacy",
            mode="shared",
            local_instances={"local-01": "local-01"},
        )


def test_remove_running_yaml_scene_stops_and_deletes_both_definitions(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    yaml_path = scenes_dir / "drill.yaml"
    yaml_path.write_text("scene_id: drill\nmode: isolated\n", encoding="utf-8")
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated")

    assert ctrl.remove("world-01", "drill", scenes_dir) is True

    assert ctrl.get("world-01", "drill") is None
    assert not yaml_path.exists()
    assert ("world-01", "drill") in store.deleted


def test_remove_runtime_only_scene_deletes_store_definition(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "runtime-scene", mode="shared")

    assert ctrl.remove("world-01", "runtime-scene", scenes_dir) is True

    assert ("world-01", "runtime-scene") in store.deleted


def test_remove_duplicate_yaml_scene_fails_before_changes(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    (scenes_dir / "first.yaml").write_text("scene_id: drill\n", encoding="utf-8")
    (scenes_dir / "second.yaml").write_text("scene_id: drill\n", encoding="utf-8")
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated")

    with pytest.raises(ValueError, match="Multiple YAML definitions"):
        ctrl.remove("world-01", "drill", scenes_dir)

    assert ctrl.get("world-01", "drill") is not None
    assert store.deleted == []


def test_remove_malformed_yaml_fails_before_changes(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    (scenes_dir / "broken.yaml").write_text("scene_id: [unterminated\n", encoding="utf-8")
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated")

    with pytest.raises(yaml.YAMLError):
        ctrl.remove("world-01", "drill", scenes_dir)

    assert ctrl.get("world-01", "drill") is not None
    assert store.deleted == []


def test_remove_yaml_delete_failure_preserves_store_definition(tmp_path, monkeypatch):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    yaml_path = scenes_dir / "drill.yaml"
    yaml_path.write_text("scene_id: drill\n", encoding="utf-8")
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated")

    def fail_unlink(self):
        raise OSError("delete failed")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(OSError, match="delete failed"):
        ctrl.remove("world-01", "drill", scenes_dir)

    assert store.load_scene("world-01", "drill") is not None
    assert store.deleted == []


def test_remove_absent_scene_returns_false(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)

    assert ctrl.remove("world-01", "missing", scenes_dir) is False
