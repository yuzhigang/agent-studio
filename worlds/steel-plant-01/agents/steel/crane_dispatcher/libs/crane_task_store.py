import os
import sqlite3


class CraneTaskStore:
    """天车任务的数据库访问层。管理 crane_tasks 表的 CRUD 操作。"""

    def __init__(self, context=None):
        self._context = context
        self._db_path = None

    def _get_db_path(self):
        if self._db_path is None:
            world_dir = self._context.get("world_dir") if self._context else None
            if not world_dir:
                raise RuntimeError("world_dir not available in lib context")
            self._db_path = os.path.join(world_dir, "runtime.db")
        return self._db_path

    def _get_world_id(self) -> str:
        if self._context and hasattr(self._context.get("this"), "world_id"):
            return self._context["this"].world_id
        return "unknown"

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
                    sequence INTEGER DEFAULT 0,
                    planned_distance INTEGER,
                    empty_distance INTEGER,
                    planned_duration INTEGER,
                    planned_start_at TEXT,
                    planned_complete_at TEXT,
                    created_at TEXT NOT NULL,
                    assigned_at TEXT,
                    transfer_point TEXT,
                    parent_task_id TEXT,
                    task_type TEXT DEFAULT 'standard',
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
            # Schema migration
            existing = {row[1] for row in conn.execute("PRAGMA table_info(crane_tasks)").fetchall()}
            for col in ("sequence", "planned_distance", "empty_distance", "planned_duration",
                        "planned_start_at", "planned_complete_at", "transfer_point", "parent_task_id", "task_type"):
                if col not in existing:
                    conn.execute(f"ALTER TABLE crane_tasks ADD COLUMN {col} INTEGER" if "distance" in col or "duration" in col or "sequence" in col else f"ALTER TABLE crane_tasks ADD COLUMN {col} TEXT")
            conn.commit()

    def create_task(self, task_id: str, from_pos: str, to_pos: str, ladle_id: str | None,
                    priority: int, created_at: str, transfer_point: str | None = None,
                    task_type: str = "standard", parent_task_id: str | None = None) -> str:
        self._ensure_table()
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO crane_tasks (world_id, task_id, from_pos, to_pos, ladle_id,
                                         status, priority, created_at, transfer_point,
                                         task_type, parent_task_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (world_id, task_id, from_pos, to_pos, ladle_id, "pending", priority,
                 created_at, transfer_point, task_type, parent_task_id),
            )
            conn.commit()
        return task_id

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

    def get_crane_assigned_queue(self, crane_id: str) -> list[dict]:
        """获取天车当前已分配的任务队列（按 sequence）。"""
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM crane_tasks
                WHERE world_id = ? AND assigned_crane = ? AND status = 'assigned'
                ORDER BY sequence ASC, created_at ASC
                """,
                (world_id, crane_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_reassignable_tasks(self, idle_crane_ids: set) -> list[dict]:
        if not idle_crane_ids:
            return []
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(idle_crane_ids))
            rows = conn.execute(
                f"""
                SELECT * FROM crane_tasks
                WHERE world_id = ? AND status = 'assigned' AND assigned_crane IN ({placeholders})
                ORDER BY priority DESC, created_at ASC
                """,
                (world_id, *idle_crane_ids),
            ).fetchall()
            return [dict(r) for r in rows]

    def apply_dispatch(self, assignments: dict[str, list[dict]], assigned_at: str) -> dict[str, list[str]]:
        """应用全局分配结果到数据库，写入计划信息。
        返回 {crane_id: [task_id, ...]} 需要发事件通知的新分配。"""
        self._ensure_table()
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        new_assignments = {}

        with sqlite3.connect(db_path) as conn:
            for crane_id, task_plans in assignments.items():
                for seq, plan in enumerate(task_plans):
                    task_id = plan["task_id"]
                    row = conn.execute(
                        "SELECT status, assigned_crane FROM crane_tasks WHERE world_id = ? AND task_id = ?",
                        (world_id, task_id),
                    ).fetchone()
                    if row is None:
                        continue
                    status, old_crane = row
                    is_new = status == "pending" or (status == "assigned" and old_crane != crane_id)

                    conn.execute(
                        """
                        UPDATE crane_tasks
                        SET status = 'assigned',
                            assigned_crane = ?,
                            sequence = ?,
                            assigned_at = ?,
                            planned_distance = ?,
                            empty_distance = ?,
                            planned_duration = ?,
                            planned_start_at = ?,
                            planned_complete_at = ?
                        WHERE world_id = ? AND task_id = ?
                        """,
                        (
                            crane_id, seq, assigned_at,
                            plan["planned_distance"],
                            plan["empty_distance"],
                            plan["planned_duration"],
                            plan["planned_start_at"],
                            plan["planned_complete_at"],
                            world_id, task_id,
                        ),
                    )

                    if is_new:
                        if crane_id not in new_assignments:
                            new_assignments[crane_id] = []
                        new_assignments[crane_id].append(task_id)

            conn.commit()

        return new_assignments

    def get_crane_queue(self, crane_id: str) -> list[dict]:
        """获取天车的已分配但未完成任务队列（按 sequence 排序）。"""
        self._ensure_table()
        world_id = self._get_world_id()
        db_path = self._get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM crane_tasks
                WHERE world_id = ? AND assigned_crane = ? AND status = 'assigned'
                ORDER BY sequence ASC, created_at ASC
                """,
                (world_id, crane_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_next_task_for_crane(self, crane_id: str) -> dict | None:
        """获取天车待执行的下一个任务（sequence 最小的 assigned 任务）。"""
        queue = self.get_crane_queue(crane_id)
        return queue[0] if queue else None

    def complete_task(self, task_id: str, completed_at: str) -> bool:
        self._ensure_table()
        world_id = self._get_world_id()
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
