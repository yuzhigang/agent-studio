import os
import subprocess
import sys
import pytest
from src.runtime.world_registry import WorldRegistry
from src.runtime.locks.world_lock import LockAlreadyHeldError


@pytest.fixture
def registry(tmp_path):
    base = str(tmp_path / "worlds")
    return WorldRegistry(base_dir=base)


def test_create_world(registry):
    world = registry.create_world("steel-01", {"name": "Steel Plant 01"})
    assert world["world_id"] == "steel-01"
    assert world["name"] == "Steel Plant 01"
    assert os.path.exists(os.path.join(registry._base_dir, "steel-01", "world.yaml"))
    assert os.path.exists(os.path.join(registry._base_dir, "steel-01", "runtime.db"))


def test_list_worlds(registry):
    registry.create_world("world-a")
    registry.create_world("world-b")
    worlds = registry.list_worlds()
    assert sorted(worlds) == ["world-a", "world-b"]


def test_load_world(registry):
    registry.create_world("world-a", {"version": 1})
    bundle = registry.load_world("world-a")
    assert bundle["world_id"] == "world-a"
    assert bundle["world_yaml"]["config"]["version"] == 1
    assert "store" in bundle
    assert "instance_manager" in bundle
    assert "scene_manager" in bundle
    assert "state_manager" in bundle


def test_load_world_raises_when_missing(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.load_world("missing-world")


def test_unload_world(registry):
    registry.create_world("world-a")
    bundle = registry.load_world("world-a")
    assert registry.unload_world("world-a") is True
    assert registry.get_loaded_world("world-a") is None
    assert registry.unload_world("world-a") is False


def test_load_world_idempotent(registry):
    registry.create_world("world-a")
    bundle1 = registry.load_world("world-a")
    bundle2 = registry.load_world("world-a")
    assert bundle1 is bundle2


def test_load_world_restores_instances(registry):
    registry.create_world("world-a")
    bundle = registry.load_world("world-a")
    im = bundle["instance_manager"]
    im.create(world_id="world-a", model_name="ladle", instance_id="ladle-001", scope="world")
    # checkpoint to persist
    bundle["state_manager"].checkpoint_world("world-a")
    # unload and reload
    registry.unload_world("world-a")
    bundle2 = registry.load_world("world-a")
    im2 = bundle2["instance_manager"]
    inst = im2.get("world-a", "ladle-001", scope="world")
    assert inst is not None
    assert inst.model_name == "ladle"


def test_load_world_acquires_lock(registry):
    registry.create_world("world-a")
    bundle = registry.load_world("world-a")
    assert bundle["lock"] is not None


def test_double_load_same_process_returns_same_bundle(registry):
    registry.create_world("world-a")
    bundle1 = registry.load_world("world-a")
    bundle2 = registry.load_world("world-a")
    assert bundle1 is bundle2


def test_concurrent_load_from_different_process_raises(registry):
    registry.create_world("world-a")
    registry.load_world("world-a")

    script = f"""
import sys
sys.path.insert(0, r"{os.getcwd()}")
from src.runtime.world_registry import WorldRegistry
try:
    reg = WorldRegistry(base_dir=r"{registry._base_dir}")
    reg.load_world("world-a")
    print("loaded")
except Exception as e:
    print(str(e))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert "already loaded" in result.stdout


def test_unload_world_releases_lock(registry):
    registry.create_world("world-a")
    registry.load_world("world-a")
    assert registry.unload_world("world-a") is True
    # should be able to load again after unload
    bundle2 = registry.load_world("world-a")
    assert bundle2 is not None
    registry.unload_world("world-a")


def test_load_world_wires_world_state_and_pre_publish_hook(registry):
    registry.create_world("ladle-proj")

    bundle = registry.load_world("ladle-proj")
    assert "world_state" in bundle
    ws = bundle["world_state"]
    im = bundle["instance_manager"]

    inst = im.create(
        world_id="ladle-proj",
        model_name="ladle",
        instance_id="ladle-001",
        scope="world",
        state={"current": "idle", "enteredAt": "2024-01-01T00:00:00Z"},
        variables={"temperature": 1500},
        model={
            "variables": {"temperature": {"type": "number", "audit": True}}
        },
    )
    # snapshot should already be computed by InstanceManager.create
    assert inst.snapshot["temperature"] == 1500

    # Publish an event from the instance and verify pre_publish_hook updates snapshot
    bus = bundle["event_bus_registry"].get_or_create("ladle-proj")
    inst.variables["temperature"] = 1600
    bus.publish("heat", {}, source="ladle-001", scope="world")
    assert inst.snapshot["temperature"] == 1600

    # Verify WorldState snapshot structure
    snapshot = ws.snapshot()
    assert "ladle" in snapshot
    assert len(snapshot["ladle"]) == 1
    assert snapshot["ladle"][0]["id"] == "ladle-001"
    assert snapshot["ladle"][0]["snapshot"]["temperature"] == 1600

    registry.unload_world("ladle-proj")
