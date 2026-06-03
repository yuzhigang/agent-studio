import importlib.util
import os
import random
import time
from datetime import datetime, timedelta, timezone

import yaml

from src.runtime.lib.decorator import lib_function

# 动态加载同目录下的 crane_task_store.py（支持 LibRegistry exec 和直接加载两种场景）
_store_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crane_task_store.py")
_store_spec = importlib.util.spec_from_file_location("_crane_task_store", _store_path)
if _store_spec is None or _store_spec.loader is None:
    raise RuntimeError(f"Failed to load crane_task_store module from {_store_path}")
_store_mod = importlib.util.module_from_spec(_store_spec)
_store_spec.loader.exec_module(_store_mod)
CraneTaskStore = _store_mod.CraneTaskStore


class CraneDispatchEngine:
    """天车调度算法引擎。负责距离计算、全局任务分配等调度逻辑。"""

    def __init__(self):
        self.__context = None
        self._store = CraneTaskStore()
        self._distance_map = None
        self._dispatch_config = None

    @property
    def _context(self):
        return self.__context

    @_context.setter
    def _context(self, value):
        self.__context = value
        self._store._context = value

    def _get_world_id(self) -> str:
        if self._context and hasattr(self._context.get("this"), "world_id"):
            return self._context["this"].world_id
        return "unknown"

    def _generate_task_id(self) -> str:
        return f"T-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _format_time(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _parse_time(self, ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _load_distance_map(self):
        if self._distance_map is not None:
            return self._distance_map
        world_dir = self._context.get("world_dir") if self._context else None
        if not world_dir:
            self._distance_map = {}
            return self._distance_map
        map_path = os.path.join(world_dir, "config", "distance_map.yaml")
        if not os.path.exists(map_path):
            self._distance_map = {}
            return self._distance_map
        with open(map_path, "r", encoding="utf-8") as f:
            self._distance_map = yaml.safe_load(f) or {}
        return self._distance_map

    def _load_dispatch_config(self):
        if self._dispatch_config is not None:
            return self._dispatch_config
        world_dir = self._context.get("world_dir") if self._context else None
        if not world_dir:
            self._dispatch_config = {"crane_speed": 1.0}
            return self._dispatch_config
        config_path = os.path.join(world_dir, "config", "dispatch_config.yaml")
        if not os.path.exists(config_path):
            self._dispatch_config = {"crane_speed": 1.0}
            return self._dispatch_config
        with open(config_path, "r", encoding="utf-8") as f:
            self._dispatch_config = yaml.safe_load(f) or {}
        return self._dispatch_config

    def _get_speed(self) -> float:
        return self._load_dispatch_config().get("crane_speed", 1.0)

    def _get_safety_gap(self) -> int:
        val = self._load_dispatch_config().get("safety_gap", 0)
        return int(val) if isinstance(val, (int, float)) else 0

    def _get_position_order(self) -> list[str]:
        val = self._load_dispatch_config().get("position_order", [])
        return list(val) if isinstance(val, list) else []

    def _get_bay_map(self) -> dict[str, list[str]]:
        val = self._load_dispatch_config().get("bay_map", {})
        return dict(val) if isinstance(val, dict) else {}

    def _get_transfer_points(self) -> dict[str, str]:
        val = self._load_dispatch_config().get("transfer_points", {})
        return dict(val) if isinstance(val, dict) else {}

    def _get_bay_for_position(self, pos: str) -> str | None:
        bay_map = self._get_bay_map()
        for bay, positions in bay_map.items():
            if pos in positions:
                return bay
        return None

    def _is_cross_bay(self, from_pos: str, to_pos: str) -> bool:
        from_bay = self._get_bay_for_position(from_pos)
        to_bay = self._get_bay_for_position(to_pos)
        return from_bay is not None and to_bay is not None and from_bay != to_bay

    def _get_transfer_point(self, from_bay: str, to_bay: str) -> str | None:
        return self._get_transfer_points().get(f"{from_bay}:{to_bay}")

    def _get_distance(self, from_pos: str, to_pos: str) -> int:
        dm = self._load_distance_map()
        if from_pos in dm and to_pos in dm[from_pos]:
            return dm[from_pos][to_pos]
        if to_pos in dm and from_pos in dm[to_pos]:
            return dm[to_pos][from_pos]
        return 999

    def _get_crane_initial_state(self, crane: dict) -> tuple[datetime, str]:
        """返回天车的初始可用时间和虚拟位置。"""
        crane_id = crane["id"]
        queue = self._store.get_crane_assigned_queue(crane_id)
        now = self._now()

        if not queue:
            # 无任务队列
            return now, crane.get("position", "park")

        # 有任务队列，找到正在执行的任务（第一个）
        first_task = queue[0]
        planned_complete = self._parse_time(first_task.get("planned_complete_at"))

        if crane.get("state") != "idle" and planned_complete:
            # 正在执行任务，可用时间 = 计划完成时间
            available_at = planned_complete if planned_complete > now else now
            virtual_pos = first_task["to_pos"]
        else:
            # idle 状态（或计划时间无效），从当前位置开始
            available_at = now
            virtual_pos = crane.get("position", "park")

        return available_at, virtual_pos

    @lib_function(module="crane_dispatch")
    def create_task(self, from_pos: str, to_pos: str, ladle_id: str | None = None, priority: int = 0) -> str:
        task_id = self._generate_task_id()
        created_at = self._format_time(self._now())
        transfer_point = None
        task_type = "standard"
        if self._is_cross_bay(from_pos, to_pos):
            from_bay = self._get_bay_for_position(from_pos)
            to_bay = self._get_bay_for_position(to_pos)
            transfer_point = self._get_transfer_point(from_bay, to_bay)
            task_type = "cross_bay_source"
        self._store.create_task(task_id, from_pos, to_pos, ladle_id, priority, created_at,
                                transfer_point=transfer_point, task_type=task_type)
        return task_id

    @lib_function(module="crane_dispatch")
    def get_task_by_id(self, task_id: str) -> dict | None:
        return self._store.get_task_by_id(task_id)

    @lib_function(module="crane_dispatch")
    def list_pending_tasks(self) -> list[dict]:
        return self._store.list_pending_tasks()

    @lib_function(module="crane_dispatch")
    def global_dispatch(self, cranes: list) -> dict[str, list[dict]]:
        """
        全局重分配所有未执行任务，考虑时间维度（预计完成时间）和同跨区防碰撞约束。
        返回 {crane_id: [task_plan, ...]}，按执行顺序排列。
        """
        self._store._ensure_table()
        self._load_distance_map()
        speed = self._get_speed()
        safety_gap = self._get_safety_gap()
        position_order = self._get_position_order()

        pending_tasks = self._store.list_pending_tasks()
        idle_crane_ids = {c["id"] for c in cranes if c.get("state") == "idle"}
        reassignable_tasks = self._store.list_reassignable_tasks(idle_crane_ids)
        all_tasks = pending_tasks + reassignable_tasks
        all_tasks.sort(key=lambda t: (-t["priority"], t["created_at"]))

        if not all_tasks:
            return {}

        # 初始化每台天车的状态
        crane_states = {}
        for c in cranes:
            avail, pos = self._get_crane_initial_state(c)
            crane_states[c["id"]] = {"available_at": avail, "virtual_pos": pos}

        # 按 bay 分组天车位置（用于防碰撞可达范围检查）
        cranes_by_id = {c["id"]: c for c in cranes}
        bay_positions = {}  # bay -> {crane_id: virtual_pos}
        for c in cranes:
            bay = c.get("bay", "")
            if bay:
                if bay not in bay_positions:
                    bay_positions[bay] = {}
                bay_positions[bay][c["id"]] = crane_states[c["id"]]["virtual_pos"]

        # 维护每个 bay 的下次可用时间（安全间隔）
        bay_next_available = {}  # bay -> datetime

        assignments = {c["id"]: [] for c in cranes}

        for task in all_tasks:
            best_crane = None
            best_complete = None
            best_plan = None

            # 跨 bay 任务：天车只执行到 transfer_point
            is_cross = task.get("task_type") == "cross_bay_source"
            effective_to = task.get("transfer_point") if is_cross else task["to_pos"]

            for crane in cranes:
                crane_id = crane["id"]
                state = crane_states[crane_id]
                bay = crane.get("bay", "")

                # --- 可达范围检查：不能越过同 bay 相邻天车 ---
                if bay and position_order:
                    my_pos = state["virtual_pos"]
                    my_idx = position_order.index(my_pos) if my_pos in position_order else -1

                    # 同 bay 其他天车的唯一位置，按顺序排列
                    other_pos_indices = sorted({
                        position_order.index(pos)
                        for pos in bay_positions.get(bay, {}).values()
                        if pos in position_order and pos != my_pos
                    })

                    to_idx = position_order.index(effective_to) if effective_to in position_order else -1
                    from_idx = position_order.index(task["from_pos"]) if task["from_pos"] in position_order else -1

                    # 左边界：比我位置小的最大索引
                    left_boundary = -1
                    for pidx in other_pos_indices:
                        if pidx < my_idx:
                            left_boundary = pidx

                    # 右边界：比我位置大的最小索引
                    right_boundary = len(position_order)
                    for pidx in reversed(other_pos_indices):
                        if pidx > my_idx:
                            right_boundary = pidx

                    if to_idx != -1 and (to_idx < left_boundary or to_idx > right_boundary):
                        continue
                    if from_idx != -1 and (from_idx < left_boundary or from_idx > right_boundary):
                        continue

                empty_dist = self._get_distance(state["virtual_pos"], task["from_pos"])
                load_dist = self._get_distance(task["from_pos"], effective_to)
                total_dist = empty_dist + load_dist
                duration = int(total_dist / speed)

                start_at = state["available_at"]

                # --- 防碰撞：同 bay 任务之间需要安全间隔 ---
                if bay and bay in bay_next_available:
                    earliest_start = bay_next_available[bay]
                    if start_at < earliest_start:
                        start_at = earliest_start

                complete_at = start_at + timedelta(minutes=duration)

                if best_complete is None or complete_at < best_complete:
                    best_crane = crane_id
                    best_complete = complete_at
                    best_plan = {
                        "task_id": task["task_id"],
                        "planned_distance": total_dist,
                        "empty_distance": empty_dist,
                        "planned_duration": duration,
                        "planned_start_at": self._format_time(start_at),
                        "planned_complete_at": self._format_time(complete_at),
                    }

            if best_crane and best_plan:
                assignments[best_crane].append(best_plan)
                # 更新天车状态
                crane_states[best_crane]["virtual_pos"] = effective_to
                crane_states[best_crane]["available_at"] = best_complete

                # 更新 bay 位置和时间线
                bay = cranes_by_id[best_crane].get("bay", "")
                if bay and best_complete is not None:
                    bay_positions.setdefault(bay, {})[best_crane] = effective_to
                    bay_next_available[bay] = best_complete + timedelta(minutes=safety_gap)

        return assignments

    @lib_function(module="crane_dispatch")
    def create_target_task(self, parent_task_id: str) -> str | None:
        """为跨 bay 任务创建目标段子任务（transfer_point -> to_pos）。"""
        parent = self._store.get_task_by_id(parent_task_id)
        if not parent or parent.get("task_type") != "cross_bay_source":
            return None
        transfer_point = parent.get("transfer_point")
        to_pos = parent["to_pos"]
        if not transfer_point:
            return None
        task_id = self._generate_task_id()
        created_at = self._format_time(self._now())
        self._store.create_task(
            task_id, transfer_point, to_pos, parent.get("ladle_id"),
            parent.get("priority", 0), created_at,
            task_type="cross_bay_target", parent_task_id=parent_task_id,
        )
        return task_id

    @lib_function(module="crane_dispatch")
    def apply_dispatch(self, assignments: dict[str, list[dict]]) -> dict[str, list[str]]:
        """
        应用全局分配结果到数据库，写入计划信息。
        返回 {crane_id: [task_id, ...]} 需要发事件通知的新分配。
        """
        assigned_at = self._format_time(self._now())
        return self._store.apply_dispatch(assignments, assigned_at)

    @lib_function(module="crane_dispatch")
    def get_crane_queue(self, crane_id: str) -> list[dict]:
        """获取天车的已分配但未完成任务队列（按 sequence 排序）。"""
        return self._store.get_crane_queue(crane_id)

    @lib_function(module="crane_dispatch")
    def get_next_task_for_crane(self, crane_id: str) -> dict | None:
        """获取天车待执行的下一个任务（sequence 最小的 assigned 任务）。"""
        return self._store.get_next_task_for_crane(crane_id)

    @lib_function(module="crane_dispatch")
    def get_task_bays(self, task_id: str) -> dict | None:
        """获取任务涉及的跨区信息。"""
        task = self._store.get_task_by_id(task_id)
        if not task:
            return None
        return {
            "from_bay": self._get_bay_for_position(task["from_pos"]),
            "to_bay": self._get_bay_for_position(task["to_pos"]),
            "transfer_point": task.get("transfer_point"),
            "task_type": task.get("task_type"),
        }

    @lib_function(module="crane_dispatch")
    def complete_task(self, task_id: str) -> bool:
        completed_at = self._format_time(self._now())
        return self._store.complete_task(task_id, completed_at)


# 向后兼容别名
CraneDispatchLib = CraneDispatchEngine
