import os
import pytest
import yaml

from src.runtime.world_registry import WorldRegistry


def _write_yaml(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


@pytest.fixture
def registry(tmp_path):
    base = str(tmp_path / "worlds")
    return WorldRegistry(base_dir=base)


@pytest.fixture
def registry_with_globals(tmp_path):
    base = str(tmp_path / "worlds")
    globals_dir = str(tmp_path / "global_models")
    return WorldRegistry(base_dir=base, global_model_paths=[globals_dir])


def test_load_world_creates_instances_from_declarations(registry):
    """World with agents/ dir should auto-create instances from declarations."""
    registry.create_world("test-world")
    world_dir = os.path.join(registry._base_dir, "test-world")

    # Write a model
    model_dir = os.path.join(world_dir, "agents", "sensor", "model")
    _write_yaml(os.path.join(model_dir, "index.yaml"), {
        "metadata": {"name": "Temperature Sensor"},
        "variables": {
            "threshold": {"type": "number", "default": 100},
            "label": {"type": "string", "default": "default-label"},
        },
        "attributes": {
            "location": {"type": "string", "default": "unknown"},
        },
    })

    # Write an instance declaration with overrides
    instances_dir = os.path.join(world_dir, "agents", "sensor", "instances")
    _write_yaml(os.path.join(instances_dir, "sensor-01.instance.yaml"), {
        "id": "sensor-01",
        "modelId": "sensor",
        "variables": {"threshold": 150, "label": "overridden-label"},
        "attributes": {"location": "boiler-room"},
        "state": "active",
    })

    bundle = registry.load_world("test-world")
    im = bundle["instance_manager"]

    inst = im.get("test-world", "sensor-01", scope="world")
    assert inst is not None
    assert inst.model_name == "sensor"
    assert inst._agent_namespace == "sensor"
    assert inst.variables["threshold"] == 150
    assert inst.variables["label"] == "overridden-label"
    assert inst.attributes["location"] == "boiler-room"
    assert inst.state["current"] == "active"
    assert bundle["instance_manager"]._sandbox.registry is bundle["lib_registry"]


def test_load_world_skips_missing_model(registry):
    """Declaration referencing a missing modelId should be skipped with a warning."""
    registry.create_world("test-world")
    world_dir = os.path.join(registry._base_dir, "test-world")

    instances_dir = os.path.join(world_dir, "agents", "ghost", "instances")
    _write_yaml(os.path.join(instances_dir, "ghost-01.instance.yaml"), {
        "id": "ghost-01",
        "modelId": "nonexistent-model",
    })

    bundle = registry.load_world("test-world")
    im = bundle["instance_manager"]

    assert im.get("test-world", "ghost-01", scope="world") is None


def test_load_world_no_agents_dir(registry):
    """World with no agents/ directory should load normally with empty instances."""
    registry.create_world("test-world")
    bundle = registry.load_world("test-world")
    im = bundle["instance_manager"]

    assert im.list_by_world("test-world") == []


def test_load_world_uses_global_model_when_not_in_world(registry_with_globals, tmp_path):
    """Model not found in world should fall back to global_model_paths."""
    registry = registry_with_globals
    registry.create_world("test-world")
    world_dir = os.path.join(registry._base_dir, "test-world")

    # Write a global model (not inside the world)
    global_models_dir = tmp_path / "global_models"
    model_dir = global_models_dir / "shared-agent" / "model"
    _write_yaml(str(model_dir / "index.yaml"), {
        "metadata": {"name": "Shared Agent"},
        "variables": {
            "counter": {"type": "number", "default": 0},
        },
    })

    # Write an instance declaration in the world referencing the global model
    instances_dir = os.path.join(world_dir, "agents", "shared-agent", "instances")
    _write_yaml(os.path.join(instances_dir, "shared-01.instance.yaml"), {
        "id": "shared-01",
        "modelId": "shared-agent",
        "variables": {"counter": 42},
    })

    bundle = registry.load_world("test-world")
    im = bundle["instance_manager"]

    inst = im.get("test-world", "shared-01", scope="world")
    assert inst is not None
    assert inst.model_name == "shared-agent"
    assert inst._agent_namespace == "shared-agent"
    assert inst.variables["counter"] == 42


def test_load_world_uses_group_agent_path_as_default_lib_namespace(registry):
    registry.create_world("test-world")
    world_dir = os.path.join(registry._base_dir, "test-world")

    model_dir = os.path.join(world_dir, "agents", "logistics", "ladle", "model")
    _write_yaml(os.path.join(model_dir, "index.yaml"), {
        "metadata": {"name": "Ladle"},
        "behaviors": {
            "dispatch": {
                "trigger": {"type": "event", "name": "run"},
                "actions": [
                    {
                        "type": "runScript",
                        "script": "result = lib.dispatcher.get_candidates({'converterId': 'C01'})",
                    }
                ],
            }
        },
    })
    libs_dir = os.path.join(world_dir, "agents", "logistics", "ladle", "libs")
    os.makedirs(libs_dir, exist_ok=True)
    with open(os.path.join(libs_dir, "dispatcher.py"), "w", encoding="utf-8") as f:
        f.write(
            "from src.runtime.lib.decorator import lib_function\n"
            "@lib_function()\n"
            "def get_candidates(args):\n"
            "    return {'candidates': []}\n"
        )
    instances_dir = os.path.join(world_dir, "agents", "logistics", "ladle", "instances")
    _write_yaml(os.path.join(instances_dir, "ladle-01.instance.yaml"), {
        "id": "ladle-01",
        "modelId": "ladle",
    })

    bundle = registry.load_world("test-world")
    inst = bundle["instance_manager"].get("test-world", "ladle-01", scope="world")

    assert inst is not None
    assert inst._agent_namespace == "logistics.ladle"

    context = bundle["instance_manager"]._build_behavior_context(inst, payload={}, source="test")
    result = bundle["instance_manager"]._sandbox.execute(
        "result = lib.dispatcher.get_candidates({'converterId': 'C01'})",
        context,
    )
    assert result == {"candidates": []}
