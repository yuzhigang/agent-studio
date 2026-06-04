import os
import sqlite3

import pytest
from src.runtime.stores.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    world_dir = str(tmp_path / "world-01")
    s = SQLiteStore(world_dir)
    yield s
    s.close()


def test_save_and_load_world(store):
    store.save_world("world-01", {"name": "Steel Plant", "version": 1})
    world = store.load_world("world-01")
    assert world is not None
    assert world["world_id"] == "world-01"
    assert world["config"]["name"] == "Steel Plant"


def test_update_world(store):
    store.save_world("world-01", {"name": "Steel Plant"})
    store.save_world("world-01", {"name": "Steel Plant 2"})
    world = store.load_world("world-01")
    assert world["config"]["name"] == "Steel Plant 2"


def test_delete_world(store):
    store.save_world("world-01", {})
    assert store.delete_world("world-01") is True
    assert store.load_world("world-01") is None
    assert store.delete_world("world-01") is False


def test_save_and_load_scene(store):
    store.save_scene("world-01", "scene-1", {
        "mode": "shared",
        "refs": ["ladle-001"],
        "local_instances": {"tmp-01": {"modelName": "inspector"}},
    })
    scene = store.load_scene("world-01", "scene-1")
    assert scene is not None
    assert scene["mode"] == "shared"
    assert scene["refs"] == ["ladle-001"]
    assert scene["local_instances"]["tmp-01"]["modelName"] == "inspector"


def test_list_scenes(store):
    store.save_scene("world-01", "scene-1", {"mode": "shared", "refs": [], "local_instances": {}})
    store.save_scene("world-01", "scene-2", {"mode": "isolated", "refs": [], "local_instances": {}})
    scenes = store.list_scenes("world-01")
    assert len(scenes) == 2
    assert {s["scene_id"] for s in scenes} == {"scene-1", "scene-2"}


def test_delete_scene(store):
    store.save_scene("world-01", "scene-1", {"mode": "shared", "refs": [], "local_instances": {}})
    assert store.delete_scene("world-01", "scene-1") is True
    assert store.load_scene("world-01", "scene-1") is None
    assert store.delete_scene("world-01", "scene-1") is False


def test_save_and_load_instance(store):
    store.save_instance("world-01", "inst-1", "world", {
        "model_name": "ladle",
        "agent_namespace": "logistics.ladle",
        "model_version": "1.0",
        "attributes": {"capacity": 200},
        "state": {"current": "idle"},
        "variables": {"steelAmount": 180},
        "bindings": {"orders": {"dataset": "active-orders"}},
        "links": {"caster": "c03"},
        "memory": {"history": []},
        "audit": {"version": 1},
        "lifecycle_state": "active",
        "updated_at": "2024-01-01T00:00:00+00:00",
    })
    inst = store.load_instance("world-01", "inst-1", "world")
    assert inst is not None
    assert inst["model_name"] == "ladle"
    assert inst["agent_namespace"] == "logistics.ladle"
    assert inst["model_version"] == "1.0"
    assert inst["attributes"]["capacity"] == 200
    assert inst["bindings"] == {"orders": {"dataset": "active-orders"}}
    assert inst["lifecycle_state"] == "active"
    assert store.list_instances("world-01")[0]["bindings"] == {
        "orders": {"dataset": "active-orders"}
    }


def test_list_instances_with_filters(store):
    store.save_instance("world-01", "inst-1", "world", {
        "model_name": "ladle",
        "lifecycle_state": "active",
    })
    store.save_instance("world-01", "inst-2", "scene:s1", {
        "model_name": "caster",
        "lifecycle_state": "completed",
    })
    all_insts = store.list_instances("world-01")
    assert len(all_insts) == 2

    scoped = store.list_instances("world-01", scope="scene:s1")
    assert len(scoped) == 1
    assert scoped[0]["instance_id"] == "inst-2"

    active = store.list_instances("world-01", lifecycle_state="active")
    assert len(active) == 1
    assert active[0]["instance_id"] == "inst-1"


def test_delete_instance(store):
    store.save_instance("world-01", "inst-1", "world", {"model_name": "ladle"})
    assert store.delete_instance("world-01", "inst-1", "world") is True
    assert store.load_instance("world-01", "inst-1", "world") is None
    assert store.delete_instance("world-01", "inst-1", "world") is False


def test_event_log_append_and_replay(store):
    store.append("world-01", "evt-1", "ladleLoaded", {"amount": 100}, "src-1", "world")
    store.append("world-01", "evt-2", "ladleLoaded", {"amount": 200}, "src-2", "world")
    events = store.replay_after("world-01", None)
    assert len(events) == 2
    assert events[0]["event_id"] == "evt-1"
    assert events[1]["payload"]["amount"] == 200


def test_event_log_replay_after_event_id(store):
    store.append("world-01", "evt-1", "ladleLoaded", {"amount": 100}, "src-1", "world")
    store.append("world-01", "evt-2", "ladleLoaded", {"amount": 200}, "src-2", "world")
    events = store.replay_after("world-01", "evt-1")
    assert len(events) == 1
    assert events[0]["event_id"] == "evt-2"


def test_event_log_replay_after_missing_raises(store):
    with pytest.raises(ValueError, match="not found"):
        store.replay_after("world-01", "missing-evt")


def test_upsert_instance(store):
    store.save_instance("world-01", "inst-1", "world", {
        "model_name": "ladle",
        "lifecycle_state": "active",
    })
    store.save_instance("world-01", "inst-1", "world", {
        "model_name": "ladle-v2",
        "lifecycle_state": "completed",
    })
    inst = store.load_instance("world-01", "inst-1", "world")
    assert inst["model_name"] == "ladle-v2"
    assert inst["lifecycle_state"] == "completed"


def test_db_file_created_in_world_dir(tmp_path):
    world_dir = str(tmp_path / "world-x")
    s = SQLiteStore(world_dir)
    assert os.path.exists(os.path.join(world_dir, "runtime.db"))
    s.close()


def test_existing_instance_table_is_migrated_with_empty_bindings(tmp_path):
    world_dir = str(tmp_path / "world-old")
    os.makedirs(world_dir)
    conn = sqlite3.connect(os.path.join(world_dir, "runtime.db"))
    conn.execute(
        """
        CREATE TABLE instances (
            world_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            model_name TEXT NOT NULL,
            agent_namespace TEXT,
            model_version TEXT,
            attributes TEXT NOT NULL,
            state TEXT NOT NULL,
            variables TEXT NOT NULL,
            links TEXT NOT NULL,
            memory TEXT NOT NULL,
            audit TEXT NOT NULL,
            lifecycle_state TEXT DEFAULT 'active',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (world_id, instance_id, scope)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO instances (
            world_id, instance_id, scope, model_name, attributes, state,
            variables, links, memory, audit, lifecycle_state, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "world-old",
            "inst-1",
            "world",
            "ladle",
            "{}",
            "{}",
            "{}",
            "{}",
            "{}",
            "{}",
            "active",
            "2024-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    store = SQLiteStore(world_dir)
    try:
        assert store.load_instance("world-old", "inst-1", "world")["bindings"] == {}
    finally:
        store.close()
