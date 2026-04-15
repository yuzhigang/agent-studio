import os
import pytest
from src.runtime.stores.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    project_dir = str(tmp_path / "proj-01")
    s = SQLiteStore(project_dir)
    yield s
    s.close()


def test_save_and_load_project(store):
    store.save_project("proj-01", {"name": "Steel Plant", "version": 1})
    proj = store.load_project("proj-01")
    assert proj is not None
    assert proj["project_id"] == "proj-01"
    assert proj["config"]["name"] == "Steel Plant"


def test_update_project(store):
    store.save_project("proj-01", {"name": "Steel Plant"})
    store.save_project("proj-01", {"name": "Steel Plant 2"})
    proj = store.load_project("proj-01")
    assert proj["config"]["name"] == "Steel Plant 2"


def test_delete_project(store):
    store.save_project("proj-01", {})
    assert store.delete_project("proj-01") is True
    assert store.load_project("proj-01") is None
    assert store.delete_project("proj-01") is False


def test_save_and_load_scene(store):
    store.save_scene("proj-01", "scene-1", {
        "mode": "shared",
        "refs": ["ladle-001"],
        "local_instances": {"tmp-01": {"modelName": "inspector"}},
    })
    scene = store.load_scene("proj-01", "scene-1")
    assert scene is not None
    assert scene["mode"] == "shared"
    assert scene["refs"] == ["ladle-001"]
    assert scene["local_instances"]["tmp-01"]["modelName"] == "inspector"


def test_list_scenes(store):
    store.save_scene("proj-01", "scene-1", {"mode": "shared", "refs": [], "local_instances": {}})
    store.save_scene("proj-01", "scene-2", {"mode": "isolated", "refs": [], "local_instances": {}})
    scenes = store.list_scenes("proj-01")
    assert len(scenes) == 2
    assert {s["scene_id"] for s in scenes} == {"scene-1", "scene-2"}


def test_delete_scene(store):
    store.save_scene("proj-01", "scene-1", {"mode": "shared", "refs": [], "local_instances": {}})
    assert store.delete_scene("proj-01", "scene-1") is True
    assert store.load_scene("proj-01", "scene-1") is None
    assert store.delete_scene("proj-01", "scene-1") is False


def test_save_and_load_instance(store):
    store.save_instance("proj-01", "inst-1", "project", {
        "model_name": "ladle",
        "model_version": "1.0",
        "attributes": {"capacity": 200},
        "state": {"current": "idle"},
        "variables": {"steelAmount": 180},
        "links": {"caster": "c03"},
        "memory": {"history": []},
        "audit": {"version": 1},
        "lifecycle_state": "active",
        "updated_at": "2024-01-01T00:00:00+00:00",
    })
    inst = store.load_instance("proj-01", "inst-1", "project")
    assert inst is not None
    assert inst["model_name"] == "ladle"
    assert inst["model_version"] == "1.0"
    assert inst["attributes"]["capacity"] == 200
    assert inst["lifecycle_state"] == "active"


def test_list_instances_with_filters(store):
    store.save_instance("proj-01", "inst-1", "project", {
        "model_name": "ladle",
        "lifecycle_state": "active",
    })
    store.save_instance("proj-01", "inst-2", "scene:s1", {
        "model_name": "caster",
        "lifecycle_state": "completed",
    })
    all_insts = store.list_instances("proj-01")
    assert len(all_insts) == 2

    scoped = store.list_instances("proj-01", scope="scene:s1")
    assert len(scoped) == 1
    assert scoped[0]["instance_id"] == "inst-2"

    active = store.list_instances("proj-01", lifecycle_state="active")
    assert len(active) == 1
    assert active[0]["instance_id"] == "inst-1"


def test_delete_instance(store):
    store.save_instance("proj-01", "inst-1", "project", {"model_name": "ladle"})
    assert store.delete_instance("proj-01", "inst-1", "project") is True
    assert store.load_instance("proj-01", "inst-1", "project") is None
    assert store.delete_instance("proj-01", "inst-1", "project") is False


def test_event_log_append_and_replay(store):
    store.append("proj-01", "evt-1", "ladleLoaded", {"amount": 100}, "src-1", "project")
    store.append("proj-01", "evt-2", "ladleLoaded", {"amount": 200}, "src-2", "project")
    events = store.replay_after("proj-01", None)
    assert len(events) == 2
    assert events[0]["event_id"] == "evt-1"
    assert events[1]["payload"]["amount"] == 200


def test_event_log_replay_after_event_id(store):
    store.append("proj-01", "evt-1", "ladleLoaded", {"amount": 100}, "src-1", "project")
    store.append("proj-01", "evt-2", "ladleLoaded", {"amount": 200}, "src-2", "project")
    events = store.replay_after("proj-01", "evt-1")
    assert len(events) == 1
    assert events[0]["event_id"] == "evt-2"


def test_event_log_replay_after_missing_raises(store):
    with pytest.raises(ValueError, match="not found"):
        store.replay_after("proj-01", "missing-evt")


def test_upsert_instance(store):
    store.save_instance("proj-01", "inst-1", "project", {
        "model_name": "ladle",
        "lifecycle_state": "active",
    })
    store.save_instance("proj-01", "inst-1", "project", {
        "model_name": "ladle-v2",
        "lifecycle_state": "completed",
    })
    inst = store.load_instance("proj-01", "inst-1", "project")
    assert inst["model_name"] == "ladle-v2"
    assert inst["lifecycle_state"] == "completed"


def test_db_file_created_in_project_dir(tmp_path):
    project_dir = str(tmp_path / "proj-x")
    s = SQLiteStore(project_dir)
    assert os.path.exists(os.path.join(project_dir, "runtime.db"))
    s.close()
