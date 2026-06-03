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
        with open(os.path.join(config_dir, "dispatch_config.yaml"), "w") as f:
            f.write("""crane_speed: 1.0\nsafety_gap: 2\nposition_order:\n  - \"A\"\n  - \"B\"\n  - \"C\"\nbay_map:\n  Bay-A:\n    - A\n  Bay-B:\n    - C\ntransfer_points:\n  Bay-A:Bay-B: B\n  Bay-B:Bay-A: B\n""")
        yield tmpdir
    finally:
        import shutil
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

    def test_list_pending_tasks(self, lib):
        lib.create_task("A", "B", "L01")
        lib.create_task("B", "C", "L02")
        pending = lib.list_pending_tasks()
        assert len(pending) == 2

    def test_global_dispatch_plans_distance_and_duration(self, lib):
        # A -> B: distance 2, speed 1.0 → duration 2
        t1 = lib.create_task("A", "B", "L01", 0)

        cranes = [
            {"id": "C1", "state": "idle", "position": "A"},
        ]
        assignments = lib.global_dispatch(cranes)
        plans = assignments["C1"]
        assert len(plans) == 1
        plan = plans[0]
        assert plan["task_id"] == t1
        assert plan["planned_distance"] == 2  # A->B = 2
        assert plan["empty_distance"] == 0     # C1 at A, task from A
        assert plan["planned_duration"] == 2   # 2 / 1.0 = 2
        assert "planned_start_at" in plan
        assert "planned_complete_at" in plan

    def test_global_dispatch_prefers_closer_crane_by_time(self, lib):
        # Task from B
        t1 = lib.create_task("B", "A", "L01", 0)

        cranes = [
            {"id": "C1", "state": "idle", "position": "A"},  # empty_dist to B = 2, total = 2+2=4
            {"id": "C2", "state": "idle", "position": "C"},  # empty_dist to B = 3, total = 3+2=5
        ]
        assignments = lib.global_dispatch(cranes)
        # C1 has shorter total distance (4 < 5), so completes earlier
        assert t1 in [p["task_id"] for p in assignments["C1"]]

    def test_global_dispatch_considers_queue_time(self, lib):
        # 2 tasks from A
        t1 = lib.create_task("A", "B", "L01", 0)
        t2 = lib.create_task("A", "B", "L02", 0)

        cranes = [
            {"id": "C1", "state": "idle", "position": "A"},
            {"id": "C2", "state": "idle", "position": "A"},
        ]
        assignments = lib.global_dispatch(cranes)
        # Both cranes at A with same distance, tasks should spread
        # because second task on same crane has to wait for first to complete
        c1_count = len(assignments.get("C1", []))
        c2_count = len(assignments.get("C2", []))
        assert c1_count + c2_count == 2
        # Due to time-based cost, tasks should spread (both get 1)
        assert c1_count == 1
        assert c2_count == 1

    def test_global_dispatch_reassigns_idle_crane(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        # Manually assign to C1
        lib.apply_dispatch({"C1": [{"task_id": t1, "planned_distance": 2, "empty_distance": 0,
                                      "planned_duration": 2, "planned_start_at": "2024-01-01T00:00:00Z",
                                      "planned_complete_at": "2024-01-01T00:02:00Z"}]})

        # Now C1 is idle but has assigned task
        t2 = lib.create_task("C", "A", "L02", 0)

        cranes = [
            {"id": "C1", "state": "idle", "position": "A"},
            {"id": "C2", "state": "idle", "position": "C"},
        ]
        assignments = lib.global_dispatch(cranes)
        # t2 from C: C2 at C gets it (empty_dist=0) vs C1 at A (empty_dist=5)
        assert t2 in [p["task_id"] for p in assignments["C2"]]

    def test_apply_dispatch_returns_only_changes(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        plan = {"task_id": t1, "planned_distance": 2, "empty_distance": 0,
                "planned_duration": 2, "planned_start_at": "2024-01-01T00:00:00Z",
                "planned_complete_at": "2024-01-01T00:02:00Z"}
        new1 = lib.apply_dispatch({"C1": [plan]})
        assert t1 in new1["C1"]

        # Same dispatch again
        new2 = lib.apply_dispatch({"C1": [plan]})
        assert "C1" not in new2 or t1 not in new2.get("C1", [])

    def test_get_crane_queue(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        t2 = lib.create_task("B", "C", "L02", 0)
        lib.apply_dispatch({"C1": [
            {"task_id": t1, "planned_distance": 2, "empty_distance": 0,
             "planned_duration": 2, "planned_start_at": "2024-01-01T00:00:00Z",
             "planned_complete_at": "2024-01-01T00:02:00Z"},
            {"task_id": t2, "planned_distance": 3, "empty_distance": 0,
             "planned_duration": 3, "planned_start_at": "2024-01-01T00:02:00Z",
             "planned_complete_at": "2024-01-01T00:05:00Z"},
        ]})

        queue = lib.get_crane_queue("C1")
        assert len(queue) == 2
        assert queue[0]["task_id"] == t1
        assert queue[1]["task_id"] == t2

    def test_complete_task(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        lib.apply_dispatch({"C1": [
            {"task_id": t1, "planned_distance": 2, "empty_distance": 0,
             "planned_duration": 2, "planned_start_at": "2024-01-01T00:00:00Z",
             "planned_complete_at": "2024-01-01T00:02:00Z"},
        ]})
        result = lib.complete_task(t1)
        assert result is True
        task = lib.get_task_by_id(t1)
        assert task["status"] == "completed"

    def test_global_dispatch_planned_fields_persisted(self, lib):
        t1 = lib.create_task("A", "B", "L01", 0)
        cranes = [{"id": "C1", "state": "idle", "position": "A"}]
        assignments = lib.global_dispatch(cranes)
        lib.apply_dispatch(assignments)

        task = lib.get_task_by_id(t1)
        assert task["planned_distance"] == 2   # A->B = 2
        assert task["empty_distance"] == 0      # C1 at A
        assert task["planned_duration"] == 2    # 2 / 1.0 = 2
        assert task["planned_start_at"] is not None
        assert task["planned_complete_at"] is not None

    def test_global_dispatch_safety_gap_same_bay(self, lib):
        # 两台天车同 bay，任务相同
        t1 = lib.create_task("A", "B", "L01", 0)
        t2 = lib.create_task("A", "B", "L02", 0)

        cranes = [
            {"id": "C1", "state": "idle", "position": "A", "bay": "BAY1"},
            {"id": "C2", "state": "idle", "position": "A", "bay": "BAY1"},
        ]
        assignments = lib.global_dispatch(cranes)

        # 两个任务应分配到不同天车（因为同 bay 有 safety_gap=2）
        c1_count = len(assignments.get("C1", []))
        c2_count = len(assignments.get("C2", []))
        assert c1_count + c2_count == 2

        # 第二个任务的开始时间应晚于第一个任务的完成时间 + safety_gap
        plans = assignments.get("C1", []) + assignments.get("C2", [])
        starts = [lib._parse_time(p["planned_start_at"]) for p in plans]
        ends = [lib._parse_time(p["planned_complete_at"]) for p in plans]
        # 按开始时间排序
        sorted_pairs = sorted(zip(starts, ends), key=lambda x: x[0])
        # 第二个任务开始 - 第一个任务结束 >= 2 分钟
        gap = (sorted_pairs[1][0] - sorted_pairs[0][1]).total_seconds() / 60
        assert gap >= 2

    def test_global_dispatch_reachability_same_position_ok(self, lib):
        # C1 和 C2 都在 A（同 bay 同位置），任务 A->B
        # 同位置天车不应互相阻塞
        t1 = lib.create_task("A", "B", "L01", 0)

        cranes = [
            {"id": "C1", "state": "idle", "position": "A", "bay": "BAY1"},
            {"id": "C2", "state": "idle", "position": "A", "bay": "BAY1"},
        ]
        assignments = lib.global_dispatch(cranes)

        # 任务应分配给其中一台（不会被同位置阻塞）
        c1_tasks = [p["task_id"] for p in assignments.get("C1", [])]
        c2_tasks = [p["task_id"] for p in assignments.get("C2", [])]
        assert t1 in c1_tasks or t1 in c2_tasks

    def test_create_task_cross_bay_detected(self, lib):
        # A 在 Bay-A，C 在 Bay-B，A->C 是跨 bay 任务
        t1 = lib.create_task("A", "C", "L01", 0)
        task = lib.get_task_by_id(t1)
        assert task["task_type"] == "cross_bay_source"
        assert task["transfer_point"] == "B"
        assert task["from_pos"] == "A"
        assert task["to_pos"] == "C"

    def test_global_dispatch_cross_bay_to_transfer_point(self, lib):
        # A->C 跨 bay，transfer_point=B
        # 源 bay 天车在 Bay-A，任务应只调度到 B
        t1 = lib.create_task("A", "C", "L01", 0)
        cranes = [
            {"id": "C1", "state": "idle", "position": "A", "bay": "Bay-A"},
        ]
        assignments = lib.global_dispatch(cranes)
        plans = assignments["C1"]
        assert len(plans) == 1
        plan = plans[0]
        assert plan["task_id"] == t1
        # A->B = 2，不是 A->C = 5
        assert plan["planned_distance"] == 2

    def test_create_target_task(self, lib):
        # 创建跨 bay 源任务
        t1 = lib.create_task("A", "C", "L01", 0)
        # 创建目标段子任务
        t2 = lib.create_target_task(t1)
        assert t2 is not None
        task = lib.get_task_by_id(t2)
        assert task["from_pos"] == "B"
        assert task["to_pos"] == "C"
        assert task["task_type"] == "cross_bay_target"
        assert task["parent_task_id"] == t1

    def test_lib_registration(self, temp_world_dir):
        mod = _load_crane_dispatch()
        assert hasattr(mod, "CraneDispatchLib")
        assert hasattr(mod.CraneDispatchLib.global_dispatch, "_lib_meta")
        assert hasattr(mod.CraneDispatchLib.apply_dispatch, "_lib_meta")
