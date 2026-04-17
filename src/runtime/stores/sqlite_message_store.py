import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from src.runtime.stores.base import MessageStore


class SQLiteMessageStore(MessageStore):
    def __init__(self, store_dir: str):
        self._store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        db_path = os.path.join(store_dir, "messagebox.db")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            source TEXT,
            scope TEXT DEFAULT 'project',
            target TEXT,
            received_at TEXT NOT NULL,
            processed_at TEXT,
            acked_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_inbox_processed_at ON inbox(processed_at);

        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            source TEXT NOT NULL,
            scope TEXT NOT NULL,
            target TEXT,
            created_at TEXT NOT NULL,
            published_at TEXT,
            error_count INTEGER DEFAULT 0,
            retry_after TEXT,
            last_error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_outbox_published_at ON outbox(published_at, error_count, retry_after);
        """
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def inbox_enqueue(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        now = self._now()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO inbox (event_type, payload, source, scope, target, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    source,
                    scope,
                    target,
                    now,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def inbox_mark_processed(self, message_id: int) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                "UPDATE inbox SET processed_at = ? WHERE id = ?",
                (now, message_id),
            )
            self._conn.commit()

    def inbox_read_pending(self, limit: int) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT id, event_type, payload, source, scope, target, received_at
            FROM inbox
            WHERE processed_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "event_type": r[1],
                "payload": json.loads(r[2]),
                "source": r[3],
                "scope": r[4],
                "target": r[5],
                "received_at": r[6],
            }
            for r in rows
        ]

    def outbox_enqueue(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
    ) -> int:
        now = self._now()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO outbox (event_type, payload, source, scope, target, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    source,
                    scope,
                    target,
                    now,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def outbox_mark_sent(self, message_id: int) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                "UPDATE outbox SET published_at = ? WHERE id = ?",
                (now, message_id),
            )
            self._conn.commit()

    def outbox_read_pending(self, limit: int) -> list[dict]:
        now = self._now()
        rows = self._conn.execute(
            """
            SELECT id, event_type, payload, source, scope, target, created_at, error_count, retry_after, last_error
            FROM outbox
            WHERE published_at IS NULL
              AND (retry_after IS NULL OR retry_after <= ?)
            ORDER BY id ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()
        return [
            {
                "id": r[0],
                "event_type": r[1],
                "payload": json.loads(r[2]),
                "source": r[3],
                "scope": r[4],
                "target": r[5],
                "created_at": r[6],
                "error_count": r[7],
                "retry_after": r[8],
                "last_error": r[9],
            }
            for r in rows
        ]

    def outbox_update_error(
        self,
        message_id: int,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE outbox
                SET error_count = ?, retry_after = ?, last_error = ?
                WHERE id = ?
                """,
                (error_count, retry_after, last_error, message_id),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
