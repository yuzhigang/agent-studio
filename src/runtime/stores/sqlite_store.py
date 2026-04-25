import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from src.runtime.stores.base import (
    WorldStore,
    SceneStore,
    InstanceStore,
    EventLogStore,
    AlarmStore,
)


class SQLiteStore(WorldStore, SceneStore, InstanceStore, EventLogStore, AlarmStore):
    def __init__(self, world_dir: str):
        self._world_dir = world_dir
        os.makedirs(world_dir, exist_ok=True)
        db_path = os.path.join(world_dir, "runtime.db")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS worlds (
            world_id TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scenes (
            world_id TEXT NOT NULL,
            scene_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            refs TEXT NOT NULL,
            local_instances TEXT NOT NULL,
            last_event_id TEXT,
            checkpointed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (world_id, scene_id)
        );

        CREATE TABLE IF NOT EXISTS instances (
            world_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            model_name TEXT NOT NULL,
            agent_namespace TEXT,
            model_version TEXT,
            attributes TEXT NOT NULL,
            state TEXT NOT NULL,
            variables TEXT NOT NULL,
            links TEXT NOT NULL,
            memory TEXT NOT NULL,
            audit TEXT NOT NULL,
            lifecycle_state TEXT DEFAULT 'active',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (world_id, instance_id, scope)
        );

        CREATE TABLE IF NOT EXISTS event_log (
            world_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            source TEXT NOT NULL,
            scope TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            PRIMARY KEY (world_id, event_id)
        );

        CREATE TABLE IF NOT EXISTS world_state (
            world_id TEXT PRIMARY KEY,
            last_event_id TEXT,
            checkpointed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            alarm_id TEXT NOT NULL,
            category TEXT,
            severity TEXT,
            level INTEGER,
            state TEXT NOT NULL,
            trigger_count INTEGER DEFAULT 0,
            trigger_message TEXT,
            clear_message TEXT,
            triggered_at TEXT,
            cleared_at TEXT,
            payload TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE (world_id, instance_id, alarm_id)
        );

        CREATE INDEX IF NOT EXISTS idx_alarms_triggered_at
            ON alarms (world_id, triggered_at);

        CREATE INDEX IF NOT EXISTS idx_alarms_state
            ON alarms (world_id, state);
        """
        with self._lock:
            self._conn.executescript(schema)
            columns = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(instances)").fetchall()
            }
            if "agent_namespace" not in columns:
                self._conn.execute("ALTER TABLE instances ADD COLUMN agent_namespace TEXT")
            self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # WorldStore
    def save_world(self, world_id: str, config: dict) -> None:
        now = self._now()
        config_json = json.dumps(config, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO worlds (world_id, config, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(world_id) DO UPDATE SET
                    config = excluded.config,
                    updated_at = excluded.updated_at
                """,
                (world_id, config_json, now, now),
            )
            self._conn.commit()

    def load_world(self, world_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT config, created_at, updated_at FROM worlds WHERE world_id = ?",
            (world_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "world_id": world_id,
            "config": json.loads(row[0]),
            "created_at": row[1],
            "updated_at": row[2],
        }

    def delete_world(self, world_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM worlds WHERE world_id = ?", (world_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # SceneStore
    def save_scene(self, world_id: str, scene_id: str, scene_data: dict) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scenes (
                    world_id, scene_id, mode, refs, local_instances,
                    last_event_id, checkpointed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, scene_id) DO UPDATE SET
                    mode = excluded.mode,
                    refs = excluded.refs,
                    local_instances = excluded.local_instances,
                    last_event_id = excluded.last_event_id,
                    checkpointed_at = excluded.checkpointed_at,
                    updated_at = excluded.updated_at
                """,
                (
                    world_id,
                    scene_id,
                    scene_data["mode"],
                    json.dumps(scene_data.get("refs", []), ensure_ascii=False),
                    json.dumps(scene_data.get("local_instances", {}), ensure_ascii=False),
                    scene_data.get("last_event_id"),
                    scene_data.get("checkpointed_at"),
                    scene_data.get("created_at", now),
                    now,
                ),
            )
            self._conn.commit()

    def load_scene(self, world_id: str, scene_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT mode, refs, local_instances, last_event_id, checkpointed_at,
                   created_at, updated_at
            FROM scenes WHERE world_id = ? AND scene_id = ?
            """,
            (world_id, scene_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "world_id": world_id,
            "scene_id": scene_id,
            "mode": row[0],
            "refs": json.loads(row[1]),
            "local_instances": json.loads(row[2]),
            "last_event_id": row[3],
            "checkpointed_at": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def list_scenes(self, world_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT scene_id, mode, refs, local_instances, last_event_id,
                   checkpointed_at, created_at, updated_at
            FROM scenes WHERE world_id = ?
            """,
            (world_id,),
        ).fetchall()
        return [
            {
                "world_id": world_id,
                "scene_id": r[0],
                "mode": r[1],
                "refs": json.loads(r[2]),
                "local_instances": json.loads(r[3]),
                "last_event_id": r[4],
                "checkpointed_at": r[5],
                "created_at": r[6],
                "updated_at": r[7],
            }
            for r in rows
        ]

    def delete_scene(self, world_id: str, scene_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM scenes WHERE world_id = ? AND scene_id = ?",
                (world_id, scene_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # InstanceStore
    def save_instance(
        self, world_id: str, instance_id: str, scope: str, snapshot: dict
    ) -> None:
        now = snapshot.get("updated_at") or self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO instances (
                    world_id, instance_id, scope, model_name, agent_namespace, model_version,
                    attributes, state, variables, links, memory, audit,
                    lifecycle_state, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, instance_id, scope) DO UPDATE SET
                    model_name = excluded.model_name,
                    agent_namespace = excluded.agent_namespace,
                    model_version = excluded.model_version,
                    attributes = excluded.attributes,
                    state = excluded.state,
                    variables = excluded.variables,
                    links = excluded.links,
                    memory = excluded.memory,
                    audit = excluded.audit,
                    lifecycle_state = excluded.lifecycle_state,
                    updated_at = excluded.updated_at
                """,
                (
                    world_id,
                    instance_id,
                    scope,
                    snapshot["model_name"],
                    snapshot.get("agent_namespace"),
                    snapshot.get("model_version"),
                    json.dumps(snapshot.get("attributes", {}), ensure_ascii=False),
                    json.dumps(snapshot.get("state", {}), ensure_ascii=False),
                    json.dumps(snapshot.get("variables", {}), ensure_ascii=False),
                    json.dumps(snapshot.get("links", {}), ensure_ascii=False),
                    json.dumps(snapshot.get("memory", {}), ensure_ascii=False),
                    json.dumps(snapshot.get("audit", {}), ensure_ascii=False),
                    snapshot.get("lifecycle_state", "active"),
                    now,
                ),
            )
            self._conn.commit()

    def load_instance(self, world_id: str, instance_id: str, scope: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT model_name, agent_namespace, model_version, attributes, state, variables,
                   links, memory, audit, lifecycle_state, updated_at
            FROM instances WHERE world_id = ? AND instance_id = ? AND scope = ?
            """,
            (world_id, instance_id, scope),
        ).fetchone()
        if row is None:
            return None
        return {
            "world_id": world_id,
            "instance_id": instance_id,
            "scope": scope,
            "model_name": row[0],
            "agent_namespace": row[1],
            "model_version": row[2],
            "attributes": json.loads(row[3]),
            "state": json.loads(row[4]),
            "variables": json.loads(row[5]),
            "links": json.loads(row[6]),
            "memory": json.loads(row[7]),
            "audit": json.loads(row[8]),
            "lifecycle_state": row[9],
            "updated_at": row[10],
        }

    def list_instances(
        self,
        world_id: str,
        scope: str | None = None,
        lifecycle_state: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT instance_id, scope, model_name, agent_namespace, model_version, attributes,
                   state, variables, links, memory, audit, lifecycle_state, updated_at
            FROM instances WHERE world_id = ?
        """
        params: list = [world_id]
        if scope is not None:
            query += " AND scope = ?"
            params.append(scope)
        if lifecycle_state is not None:
            query += " AND lifecycle_state = ?"
            params.append(lifecycle_state)
        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "world_id": world_id,
                "instance_id": r[0],
                "scope": r[1],
                "model_name": r[2],
                "agent_namespace": r[3],
                "model_version": r[4],
                "attributes": json.loads(r[5]),
                "state": json.loads(r[6]),
                "variables": json.loads(r[7]),
                "links": json.loads(r[8]),
                "memory": json.loads(r[9]),
                "audit": json.loads(r[10]),
                "lifecycle_state": r[11],
                "updated_at": r[12],
            }
            for r in rows
        ]

    def delete_instance(self, world_id: str, instance_id: str, scope: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM instances WHERE world_id = ? AND instance_id = ? AND scope = ?",
                (world_id, instance_id, scope),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # EventLogStore
    def append(
        self,
        world_id: str,
        event_id: str,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
    ) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO event_log (world_id, event_id, event_type, payload, source, scope, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    world_id,
                    event_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    source,
                    scope,
                    now,
                ),
            )
            self._conn.commit()

    def replay_after(self, world_id: str, last_event_id: str | None) -> list[dict]:
        if last_event_id is None:
            rows = self._conn.execute(
                """
                SELECT event_id, event_type, payload, source, scope, timestamp
                FROM event_log WHERE world_id = ? ORDER BY timestamp ASC
                """,
                (world_id,),
            ).fetchall()
        else:
            # Verify last_event_id exists
            exists = self._conn.execute(
                "SELECT 1 FROM event_log WHERE world_id = ? AND event_id = ?",
                (world_id, last_event_id),
            ).fetchone()
            if exists is None:
                raise ValueError(
                    f"last_event_id {last_event_id!r} not found in event_log for world {world_id}"
                )
            rows = self._conn.execute(
                """
                SELECT event_id, event_type, payload, source, scope, timestamp
                FROM event_log
                WHERE world_id = ? AND timestamp > (
                    SELECT timestamp FROM event_log WHERE world_id = ? AND event_id = ?
                )
                ORDER BY timestamp ASC
                """,
                (world_id, world_id, last_event_id),
            ).fetchall()
        return [
            {
                "event_id": r[0],
                "event_type": r[1],
                "payload": json.loads(r[2]),
                "source": r[3],
                "scope": r[4],
                "timestamp": r[5],
            }
            for r in rows
        ]

    # World state helpers (used by StateManager)
    def save_world_state(
        self, world_id: str, last_event_id: str | None, checkpointed_at: str
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO world_state (world_id, last_event_id, checkpointed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(world_id) DO UPDATE SET
                    last_event_id = excluded.last_event_id,
                    checkpointed_at = excluded.checkpointed_at
                """,
                (world_id, last_event_id, checkpointed_at),
            )
            self._conn.commit()

    def load_world_state(self, world_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT last_event_id, checkpointed_at FROM world_state WHERE world_id = ?",
            (world_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "world_id": world_id,
            "last_event_id": row[0],
            "checkpointed_at": row[1],
        }

    # AlarmStore
    def save_alarm(self, world_id: str, alarm_data: dict) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO alarms (
                    world_id, instance_id, alarm_id, category, severity, level,
                    state, trigger_count, trigger_message, clear_message,
                    triggered_at, cleared_at, payload, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, instance_id, alarm_id) DO UPDATE SET
                    category = excluded.category,
                    severity = excluded.severity,
                    level = excluded.level,
                    state = excluded.state,
                    trigger_count = excluded.trigger_count,
                    trigger_message = excluded.trigger_message,
                    clear_message = excluded.clear_message,
                    triggered_at = excluded.triggered_at,
                    cleared_at = excluded.cleared_at,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    world_id,
                    alarm_data["instance_id"],
                    alarm_data["alarm_id"],
                    alarm_data.get("category"),
                    alarm_data.get("severity"),
                    alarm_data.get("level"),
                    alarm_data["state"],
                    alarm_data.get("trigger_count", 0),
                    alarm_data.get("trigger_message"),
                    alarm_data.get("clear_message"),
                    alarm_data.get("triggered_at"),
                    alarm_data.get("cleared_at"),
                    json.dumps(alarm_data.get("payload", {}), ensure_ascii=False),
                    now,
                ),
            )
            self._conn.commit()

    def load_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT category, severity, level, state, trigger_count, trigger_message,
                   clear_message, triggered_at, cleared_at, payload, updated_at
            FROM alarms WHERE world_id = ? AND instance_id = ? AND alarm_id = ?
            """,
            (world_id, instance_id, alarm_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "world_id": world_id,
            "instance_id": instance_id,
            "alarm_id": alarm_id,
            "category": row[0],
            "severity": row[1],
            "level": row[2],
            "state": row[3],
            "trigger_count": row[4],
            "trigger_message": row[5],
            "clear_message": row[6],
            "triggered_at": row[7],
            "cleared_at": row[8],
            "payload": json.loads(row[9]) if row[9] else {},
            "updated_at": row[10],
        }

    def list_alarms(
        self,
        world_id: str,
        instance_id: str | None = None,
        state: str | None = None,
        triggered_after: str | None = None,
        triggered_before: str | None = None,
    ) -> list[dict]:
        # NOTE: Dynamic SQL construction below is safe only because all values
        # are passed as query parameters. Never use f-strings or .format() here.
        query = """
            SELECT world_id, instance_id, alarm_id, category, severity, level,
                   state, trigger_count, trigger_message, clear_message,
                   triggered_at, cleared_at, payload, updated_at
            FROM alarms WHERE world_id = ?
        """
        params: list = [world_id]
        if instance_id is not None:
            query += " AND instance_id = ?"
            params.append(instance_id)
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        if triggered_after is not None:
            query += " AND triggered_at >= ?"
            params.append(triggered_after)
        if triggered_before is not None:
            query += " AND triggered_at <= ?"
            params.append(triggered_before)
        query += " ORDER BY triggered_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "world_id": r[0],
                "instance_id": r[1],
                "alarm_id": r[2],
                "category": r[3],
                "severity": r[4],
                "level": r[5],
                "state": r[6],
                "trigger_count": r[7],
                "trigger_message": r[8],
                "clear_message": r[9],
                "triggered_at": r[10],
                "cleared_at": r[11],
                "payload": json.loads(r[12]) if r[12] else {},
                "updated_at": r[13],
            }
            for r in rows
        ]

    def delete_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM alarms WHERE world_id = ? AND instance_id = ? AND alarm_id = ?",
                (world_id, instance_id, alarm_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def clear_alarm(self, world_id: str, instance_id: str, alarm_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE alarms
                SET state = 'inactive', trigger_count = 0, cleared_at = ?, updated_at = ?
                WHERE world_id = ? AND instance_id = ? AND alarm_id = ? AND state = 'active'
                """,
                (self._now(), self._now(), world_id, instance_id, alarm_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
