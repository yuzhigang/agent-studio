import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.runtime.world_registry import WorldRegistry


def test_load_world_creates_alarm_manager():
    registry = WorldRegistry(base_dir="worlds", global_model_paths=["agents"])
    bundle = registry.load_world("demo-world")
    assert "alarm_manager" in bundle
    assert bundle["alarm_manager"] is not None
    registry.unload_world("demo-world")
