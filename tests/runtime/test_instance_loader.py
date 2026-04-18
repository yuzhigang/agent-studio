import os
import pytest
from src.runtime.instance_loader import InstanceLoader

WORLDS = os.path.join(os.path.dirname(__file__), "..", "fixtures", "worlds")


def test_scan_finds_instance_files():
    world_dir = os.path.join(WORLDS, "steel-plant-01")
    results = InstanceLoader.scan(world_dir)
    assert len(results) == 3
    ids = {r["id"] for r in results}
    assert ids == {"ladle-01", "ladle-02", "mp-01"}


def test_scan_multiple_namespaces():
    world_dir = os.path.join(WORLDS, "steel-plant-01")
    results = InstanceLoader.scan(world_dir)
    ids = {r["id"] for r in results}
    assert "ladle-01" in ids
    assert "ladle-02" in ids
    assert "mp-01" in ids
    assert len(results) == 3


def test_scan_no_agents_dir():
    world_dir = os.path.join(os.path.dirname(__file__), "..", "fixtures", "no_such_world")
    results = InstanceLoader.scan(world_dir)
    assert results == []


def test_scan_empty_agents_dir():
    empty_agents = os.path.join(os.path.dirname(__file__), "..", "fixtures", "empty_agents")
    os.makedirs(empty_agents, exist_ok=True)
    try:
        results = InstanceLoader.scan(empty_agents)
        assert results == []
    finally:
        os.rmdir(empty_agents)


def test_scan_includes_source_file():
    world_dir = os.path.join(WORLDS, "steel-plant-01")
    results = InstanceLoader.scan(world_dir)
    for r in results:
        assert "_source_file" in r
        assert r["_source_file"].endswith(".instance.yaml")
        assert os.path.exists(r["_source_file"])


def test_scan_skips_non_instance_yaml():
    world_dir = os.path.join(os.path.dirname(__file__), "..", "fixtures", "agents_with_config")
    instances_dir = os.path.join(world_dir, "agents", "some_agent", "instances")
    os.makedirs(instances_dir, exist_ok=True)
    try:
        with open(os.path.join(instances_dir, "config.yaml"), "w") as f:
            f.write("foo: bar\n")
        with open(os.path.join(instances_dir, "valid.instance.yaml"), "w") as f:
            f.write("id: valid\nmodelId: some_agent\n")
        results = InstanceLoader.scan(world_dir)
        ids = {r["id"] for r in results}
        assert "valid" in ids
        assert "config" not in ids
    finally:
        import shutil
        shutil.rmtree(world_dir, ignore_errors=True)
