import importlib.util
import os
import tempfile

import pytest

from src.runtime.lib.decorator import lib_function
from src.runtime.lib.registry import LibRegistry


def _load_crane_dispatch():
    """Load crane_dispatch lib module directly since the path contains hyphens."""
    lib_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "worlds", "steel-plant-01", "agents", "steel", "crane_dispatcher", "libs", "crane_dispatch.py"
    )
    lib_path = os.path.abspath(lib_path)
    spec = importlib.util.spec_from_file_location("crane_dispatch", lib_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cd_mod = _load_crane_dispatch()
CraneDispatchLib = _cd_mod.CraneDispatchLib


@pytest.fixture
def temp_world_dir():
    tmpdir = tempfile.mkdtemp()
    try:
        # Create config/distance_map.yaml
        config_dir = os.path.join(tmpdir, "config")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "distance_map.yaml"), "w") as f:
            f.write("""
A:
  A: 0
  B: 2
  C: 5
B:
  A: 2
  B: 0
  C: 3
C:
  A: 5
  B: 3
  C: 0
""")
        yield tmpdir
    finally:
        import shutil
        # On Windows, sqlite may hold file handles briefly; ignore cleanup errors
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def lib(temp_world_dir):
    instance = CraneDispatchLib()
    instance._context = {
        "this": type("MockNS", (), {"world_id": "test-world", "id": "CD1"})(),
        "world_dir": temp_world_dir,
    }
    return instance


class TestCraneDispatchLib:
    def test_create_task(self, lib):
        task_id = lib.create_task("A", "B", "L01", 1)
        assert task_id.startswith("T-")
        task = lib.get_task_by_id(task_id)
        assert task["from_pos"] == "A"
        assert task["to_pos"] == "B"
        assert task["ladle_id"] == "L01"
        assert task["priority"] == 1
        assert task["status"] == "pending"

    def test_get_next_pending_task_returns_oldest(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        t2 = lib.create_task("A", "C", "L02", 0)
        next_task = lib.get_next_pending_task()
        assert next_task["task_id"] == t1

    def test_get_next_pending_task_respects_priority(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        t2 = lib.create_task("A", "C", "L02", 5)
        next_task = lib.get_next_pending_task()
        assert next_task["task_id"] == t2

    def test_select_idle_crane_returns_none_when_all_busy(self, lib):
        cranes = [
            {"id": "C1", "state": "moving", "position": "A"},
            {"id": "C2", "state": "hoisting", "position": "B"},
        ]
        assert lib.select_idle_crane(cranes, "A") is None

    def test_select_idle_crane_prefers_same_position(self, lib):
        cranes = [
            {"id": "C1", "state": "idle", "position": "A"},
            {"id": "C2", "state": "idle", "position": "C"},
        ]
        selected = lib.select_idle_crane(cranes, "A")
        assert selected["id"] == "C1"

    def test_select_idle_crane_prefers_closer(self, lib):
        cranes = [
            {"id": "C1", "state": "idle", "position": "C"},
            {"id": "C2", "state": "idle", "position": "B"},
        ]
        selected = lib.select_idle_crane(cranes, "A")
        assert selected["id"] == "C2"  # B is closer to A (2) than C (5)

    def test_assign_task(self, lib):
        task_id = lib.create_task("A", "B", "L01")
        result = lib.assign_task(task_id, "C1")
        assert result is True
        task = lib.get_task_by_id(task_id)
        assert task["status"] == "assigned"
        assert task["assigned_crane"] == "C1"

    def test_assign_task_only_pending(self, lib):
        task_id = lib.create_task("A", "B", "L01")
        lib.assign_task(task_id, "C1")
        result = lib.assign_task(task_id, "C2")
        assert result is False  # already assigned

    def test_complete_task(self, lib):
        task_id = lib.create_task("A", "B", "L01")
        lib.assign_task(task_id, "C1")
        result = lib.complete_task(task_id)
        assert result is True
        task = lib.get_task_by_id(task_id)
        assert task["status"] == "completed"

    def test_list_pending_tasks(self, lib):
        lib.create_task("A", "B", "L01")
        lib.create_task("B", "C", "L02")
        lib.assign_task(lib.create_task("C", "A", "L03"), "C1")
        pending = lib.list_pending_tasks()
        assert len(pending) == 2

    def test_lib_registration(self, temp_world_dir):
        """Verify the lib functions are discoverable by LibRegistry."""
        mod = _load_crane_dispatch()
        assert hasattr(mod, "CraneDispatchLib")
        assert hasattr(mod.CraneDispatchLib.create_task, "_lib_meta")
