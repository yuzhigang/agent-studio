import json
import os
import random
import sqlite3
import time

import yaml

from src.runtime.lib.decorator import lib_function


class CraneDispatchLib:
    def __init__(self):
        self._context = None
        self._distance_map = None
        self._db_path = None

    def _get_db_path(self):
        if self._db_path is None:
            world_dir = self._context.get("world_dir") if self._context else None
            if not world_dir:
                raise RuntimeError("world_dir not available in lib context")
            self._db_path = os.path.join(world_dir, "runtime.db")
        return self._db_path

    def _ensure_table(self):
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crane_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    from_pos TEXT NOT NULL,
                    to_pos TEXT NOT NULL,
                    ladle_id TEXT,
                    assigned_crane TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    assigned_at TEXT,
                    completed_at TEXT,
                    UNIQUE(world_id, task_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_crane_tasks_status ON crane_tasks(world_id, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_crane_tasks_assigned ON crane_tasks(world_id, assigned_crane)"
            )
            conn.commit()

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

    def _get_distance(self, from_pos: str, to_pos: str) -> int:
        dm = self._load_distance_map()
        if from_pos in dm and to_pos in dm[from_pos]:
            return dm[from_pos][to_pos]
        if to_pos in dm and from_pos in dm[to_pos]:
            return dm[to_pos][from_pos]
        return 999  # 未知位置间给一个很大距离

    def _get_world_id(self) -> str:
        if self._context and hasattr(self._context.get("this"), "world_id"):
            return self._context["this"].world_id
        return "unknown"

    def _generate_task_id(self) -> str:
        return f"T-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"

    @lib_function(module="crane_dispatch")
    def create_task(self, from_pos: str, to_pos: str, ladle_id: str = None, priority: int = 0) -> str:
        self._ensure_table()
        task_id = self._generate_task_id()
        world_id = self._get_world_id()
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO crane_tasks (world_id, task_id, from_pos, to_pos, ladle_id, status, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (world_id, task_id, from_pos, to_pos, ladle_id, "pending", priority, created_at),
            )
            conn.commit()
        return task_id

    @lib_function(module="crane_dispatch")
    def get_next_pending_task(self) -> dict | None:
        self._ensure_table()
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM crane_tasks
                WHERE world_id = ? AND status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (world_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    @lib_function(module="crane_dispatch")
    def select_idle_crane(self, cranes: list, from_pos: str) -> dict | None:
        """从 idle 状态的天车中选择离 from_pos 最近的一台。"""
        idle_cranes = [c for c in cranes if c.get("state") == "idle"]
        if not idle_cranes:
            return None
        self._load_distance_map()
        best = None
        best_dist = None
        for crane in idle_cranes:
            crane_pos = crane.get("position", "")
            dist = self._get_distance(from_pos, crane_pos)
            if best_dist is None or dist < best_dist:
                best = crane
                best_dist = dist
        return best

    @lib_function(module="crane_dispatch")
    def assign_task(self, task_id: str, crane_id: str) -> bool:
        self._ensure_table()
        world_id = self._get_world_id()
        assigned_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                """
                UPDATE crane_tasks
                SET status = 'assigned', assigned_crane = ?, assigned_at = ?
                WHERE world_id = ? AND task_id = ? AND status = 'pending'
                """,
                (crane_id, assigned_at, world_id, task_id),
            )
            conn.commit()
            return cur.rowcount > 0

    @lib_function(module="crane_dispatch")
    def complete_task(self, task_id: str) -> bool:
        self._ensure_table()
        world_id = self._get_world_id()
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                """
                UPDATE crane_tasks
                SET status = 'completed', completed_at = ?
                WHERE world_id = ? AND task_id = ? AND status = 'assigned'
                """,
                (completed_at, world_id, task_id),
            )
            conn.commit()
            return cur.rowcount > 0

    @lib_function(module="crane_dispatch")
    def list_pending_tasks(self) -> list[dict]:
        self._ensure_table()
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM crane_tasks
                WHERE world_id = ? AND status = 'pending'
                ORDER BY priority DESC, created_at ASC
                """,
                (world_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @lib_function(module="crane_dispatch")
    def get_task_by_id(self, task_id: str) -> dict | None:
        self._ensure_table()
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM crane_tasks WHERE world_id = ? AND task_id = ?",
                (world_id, task_id),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
