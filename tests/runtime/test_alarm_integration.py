import pytest
from src.runtime.world_registry import WorldRegistry


@pytest.fixture
def registry(tmp_path):
    base = tmp_path / "worlds"
    base.mkdir()
    reg = WorldRegistry(base_dir=str(base), global_model_paths=[])
    reg.create_world("test-world")
    yield reg
    reg.unload_world("test-world")


def test_load_world_creates_alarm_manager(registry):
    bundle = registry.load_world("test-world")
    assert "alarm_manager" in bundle
    assert bundle["alarm_manager"] is not None
    assert bundle["instance_manager"]._alarm_manager is bundle["alarm_manager"]
