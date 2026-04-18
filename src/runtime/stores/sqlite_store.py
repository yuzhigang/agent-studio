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
)


class SQLiteStore(WorldStore, SceneStore, InstanceStore, EventLogStore):
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
        """
        with self._lock:
            self._conn.executescript(schema)
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
                    world_id, instance_id, scope, model_name, model_version,
                    attributes, state, variables, links, memory, audit,
                    lifecycle_state, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id, instance_id, scope) DO UPDATE SET
                    model_name = excluded.model_name,
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
            SELECT model_name, model_version, attributes, state, variables,
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
            "model_version": row[1],
            "attributes": json.loads(row[2]),
            "state": json.loads(row[3]),
            "variables": json.loads(row[4]),
            "links": json.loads(row[5]),
            "memory": json.loads(row[6]),
            "audit": json.loads(row[7]),
            "lifecycle_state": row[8],
            "updated_at": row[9],
        }

    def list_instances(
        self,
        world_id: str,
        scope: str | None = None,
        lifecycle_state: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT instance_id, scope, model_name, model_version, attributes,
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
                "model_version": r[3],
                "attributes": json.loads(r[4]),
                "state": json.loads(r[5]),
                "variables": json.loads(r[6]),
                "links": json.loads(r[7]),
                "memory": json.loads(r[8]),
                "audit": json.loads(r[9]),
                "lifecycle_state": r[10],
                "updated_at": r[11],
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

    def close(self) -> None:
        with self._lock:
            self._conn.close()
