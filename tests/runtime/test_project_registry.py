import os
import pytest
from src.runtime.project_registry import ProjectRegistry


@pytest.fixture
def registry(tmp_path):
    base = str(tmp_path / "projects")
    return ProjectRegistry(base_dir=base)


def test_create_project(registry):
    proj = registry.create_project("steel-01", {"name": "Steel Plant 01"})
    assert proj["project_id"] == "steel-01"
    assert proj["name"] == "Steel Plant 01"
    assert os.path.exists(os.path.join(registry._base_dir, "steel-01", "project.yaml"))
    assert os.path.exists(os.path.join(registry._base_dir, "steel-01", "runtime.db"))


def test_list_projects(registry):
    registry.create_project("proj-a")
    registry.create_project("proj-b")
    projects = registry.list_projects()
    assert sorted(projects) == ["proj-a", "proj-b"]


def test_load_project(registry):
    registry.create_project("proj-a", {"version": 1})
    bundle = registry.load_project("proj-a")
    assert bundle["project_id"] == "proj-a"
    assert bundle["project_yaml"]["config"]["version"] == 1
    assert "store" in bundle
    assert "instance_manager" in bundle
    assert "scene_manager" in bundle
    assert "state_manager" in bundle


def test_load_project_raises_when_missing(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.load_project("missing-proj")


def test_unload_project(registry):
    registry.create_project("proj-a")
    bundle = registry.load_project("proj-a")
    assert registry.unload_project("proj-a") is True
    assert registry.get_loaded_project("proj-a") is None
    assert registry.unload_project("proj-a") is False


def test_load_project_idempotent(registry):
    registry.create_project("proj-a")
    bundle1 = registry.load_project("proj-a")
    bundle2 = registry.load_project("proj-a")
    assert bundle1 is bundle2


def test_load_project_restores_instances(registry):
    registry.create_project("proj-a")
    bundle = registry.load_project("proj-a")
    im = bundle["instance_manager"]
    im.create(project_id="proj-a", model_name="ladle", instance_id="ladle-001", scope="project")
    # checkpoint to persist
    bundle["state_manager"].checkpoint_project("proj-a")
    # unload and reload
    registry.unload_project("proj-a")
    bundle2 = registry.load_project("proj-a")
    im2 = bundle2["instance_manager"]
    inst = im2.get("proj-a", "ladle-001", scope="project")
    assert inst is not None
    assert inst.model_name == "ladle"
