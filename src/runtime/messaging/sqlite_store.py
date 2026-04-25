import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from src.runtime.messaging.envelope import MessageEnvelope
from src.runtime.messaging.store import InboxDelivery, MessageStore


class SQLiteMessageStore(MessageStore):
    def __init__(self, store_dir: str):
        os.makedirs(store_dir, exist_ok=True)
        db_path = os.path.join(store_dir, "messagebox.db")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._lock = threading.Lock()
        self._ensure_schema()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _decode_envelope_row(self, row: tuple[object, ...]) -> MessageEnvelope:
        return MessageEnvelope(
            message_id=str(row[0]),
            source_world=row[1] if row[1] is None else str(row[1]),
            target_world=row[2] if row[2] is None else str(row[2]),
            event_type=str(row[3]),
            payload=json.loads(str(row[4])),
            source=row[5] if row[5] is None else str(row[5]),
            scope=str(row[6]),
            target=row[7] if row[7] is None else str(row[7]),
            trace_id=row[8] if row[8] is None else str(row[8]),
            headers=json.loads(str(row[9])),
        )

    def _ensure_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS inbox (
            message_id TEXT PRIMARY KEY,
            source_world TEXT,
            target_world TEXT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            source TEXT,
            scope TEXT NOT NULL DEFAULT 'world',
            target TEXT,
            trace_id TEXT,
            headers TEXT NOT NULL DEFAULT '{}',
            received_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS idx_inbox_status_received_at
            ON inbox(status, received_at);

        CREATE TABLE IF NOT EXISTS inbox_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            target_world_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_count INTEGER NOT NULL DEFAULT 0,
            retry_after TEXT,
            last_error TEXT,
            delivered_at TEXT,
            UNIQUE(message_id, target_world_id),
            FOREIGN KEY(message_id) REFERENCES inbox(message_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_inbox_deliveries_status_retry
            ON inbox_deliveries(status, retry_after, id);

        CREATE TABLE IF NOT EXISTS outbox (
            message_id TEXT PRIMARY KEY,
            source_world TEXT,
            target_world TEXT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            source TEXT,
            scope TEXT NOT NULL DEFAULT 'world',
            target TEXT,
            trace_id TEXT,
            headers TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_count INTEGER NOT NULL DEFAULT 0,
            retry_after TEXT,
            last_error TEXT,
            sent_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_outbox_status_retry_created
            ON outbox(status, retry_after, created_at);
        """
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()

    def inbox_append(self, envelope: MessageEnvelope) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO inbox (
                    message_id,
                    source_world,
                    target_world,
                    event_type,
                    payload,
                    source,
                    scope,
                    target,
                    trace_id,
                    headers,
                    received_at,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    envelope.message_id,
                    envelope.source_world,
                    envelope.target_world,
                    envelope.event_type,
                    json.dumps(envelope.payload, ensure_ascii=False),
                    envelope.source,
                    envelope.scope,
                    envelope.target,
                    envelope.trace_id,
                    json.dumps(envelope.headers, ensure_ascii=False),
                    self._now(),
                ),
            )
            self._conn.commit()

    def inbox_read_pending(self, limit: int) -> list[MessageEnvelope]:
        rows = self._conn.execute(
            """
            SELECT message_id, source_world, target_world, event_type, payload, source, scope, target, trace_id, headers
            FROM inbox
            WHERE status = 'pending'
            ORDER BY received_at ASC, message_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._decode_envelope_row(row) for row in rows]

    def inbox_load(self, message_id: str) -> MessageEnvelope:
        row = self._conn.execute(
            """
            SELECT message_id, source_world, target_world, event_type, payload, source, scope, target, trace_id, headers
            FROM inbox
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"inbox message not found: {message_id}")
        return self._decode_envelope_row(row)

    def inbox_mark_expanded(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE inbox SET status = 'expanded' WHERE message_id = ?",
                (message_id,),
            )
            self._conn.commit()

    def inbox_mark_completed(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE inbox SET status = 'completed' WHERE message_id = ?",
                (message_id,),
            )
            self._conn.commit()

    def inbox_mark_failed(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE inbox SET status = 'failed' WHERE message_id = ?",
                (message_id,),
            )
            self._conn.commit()

    def inbox_create_deliveries(self, message_id: str, target_worlds: list[str]) -> None:
        rows = [(message_id, target_world) for target_world in target_worlds]
        with self._lock:
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO inbox_deliveries (message_id, target_world_id, status)
                VALUES (?, ?, 'pending')
                """,
                rows,
            )
            self._conn.commit()

    def inbox_read_pending_deliveries(self, limit: int) -> list[InboxDelivery]:
        rows = self._conn.execute(
            """
            SELECT message_id, target_world_id, status, error_count, retry_after, last_error
            FROM inbox_deliveries
            WHERE status IN ('pending', 'retry')
              AND (retry_after IS NULL OR retry_after <= ?)
            ORDER BY id ASC
            LIMIT ?
            """,
            (self._now(), limit),
        ).fetchall()
        return [
            InboxDelivery(
                message_id=str(row[0]),
                target_world=str(row[1]),
                status=str(row[2]),
                error_count=int(row[3]),
                retry_after=row[4] if row[4] is None else str(row[4]),
                last_error=row[5] if row[5] is None else str(row[5]),
            )
            for row in rows
        ]

    def inbox_mark_delivery_delivered(self, message_id: str, target_world: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'delivered',
                    delivered_at = ?,
                    retry_after = NULL,
                    last_error = NULL
                WHERE message_id = ? AND target_world_id = ?
                """,
                (self._now(), message_id, target_world),
            )
            self._conn.commit()

    def inbox_mark_delivery_retry(
        self,
        message_id: str,
        target_world: str,
        *,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'retry',
                    error_count = ?,
                    retry_after = ?,
                    last_error = ?
                WHERE message_id = ? AND target_world_id = ?
                """,
                (error_count, retry_after, last_error, message_id, target_world),
            )
            self._conn.commit()

    def inbox_mark_delivery_dead(
        self,
        message_id: str,
        target_world: str,
        *,
        error_count: int,
        last_error: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'dead',
                    error_count = ?,
                    retry_after = NULL,
                    last_error = ?
                WHERE message_id = ? AND target_world_id = ?
                """,
                (error_count, last_error, message_id, target_world),
            )
            self._conn.commit()

    def inbox_reconcile_statuses(self) -> None:
        with self._lock:
            message_ids = self._conn.execute(
                "SELECT DISTINCT message_id FROM inbox_deliveries"
            ).fetchall()
            for (message_id,) in message_ids:
                statuses = [
                    str(row[0])
                    for row in self._conn.execute(
                        "SELECT status FROM inbox_deliveries WHERE message_id = ?",
                        (message_id,),
                    ).fetchall()
                ]
                if statuses and all(status == "delivered" for status in statuses):
                    self._conn.execute(
                        "UPDATE inbox SET status = 'completed' WHERE message_id = ?",
                        (message_id,),
                    )
                elif statuses and all(
                    status in {"delivered", "dead", "failed"} for status in statuses
                ):
                    self._conn.execute(
                        "UPDATE inbox SET status = 'failed' WHERE message_id = ?",
                        (message_id,),
                    )
            self._conn.commit()

    def inbox_mark_world_deliveries_dead(self, target_world: str, *, last_error: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'dead',
                    retry_after = NULL,
                    last_error = ?
                WHERE target_world_id = ?
                  AND status IN ('pending', 'retry')
                """,
                (last_error, target_world),
            )
            self._conn.commit()

    def outbox_append(self, envelope: MessageEnvelope) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO outbox (
                    message_id,
                    source_world,
                    target_world,
                    event_type,
                    payload,
                    source,
                    scope,
                    target,
                    trace_id,
                    headers,
                    created_at,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    envelope.message_id,
                    envelope.source_world,
                    envelope.target_world,
                    envelope.event_type,
                    json.dumps(envelope.payload, ensure_ascii=False),
                    envelope.source,
                    envelope.scope,
                    envelope.target,
                    envelope.trace_id,
                    json.dumps(envelope.headers, ensure_ascii=False),
                    self._now(),
                ),
            )
            self._conn.commit()

    def outbox_read_pending(self, limit: int) -> list[MessageEnvelope]:
        rows = self._conn.execute(
            """
            SELECT message_id, source_world, target_world, event_type, payload, source, scope, target, trace_id, headers
            FROM outbox
            WHERE status IN ('pending', 'retry')
              AND (retry_after IS NULL OR retry_after <= ?)
            ORDER BY created_at ASC, message_id ASC
            LIMIT ?
            """,
            (self._now(), limit),
        ).fetchall()
        return [self._decode_envelope_row(row) for row in rows]

    def outbox_get_error_count(self, message_id: str) -> int:
        row = self._conn.execute(
            "SELECT error_count FROM outbox WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def outbox_mark_sent(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE outbox
                SET status = 'sent',
                    sent_at = ?,
                    retry_after = NULL,
                    last_error = NULL
                WHERE message_id = ?
                """,
                (self._now(), message_id),
            )
            self._conn.commit()

    def outbox_mark_retry(
        self,
        message_id: str,
        *,
        error_count: int,
        retry_after: str | None,
        last_error: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE outbox
                SET status = 'retry',
                    error_count = ?,
                    retry_after = ?,
                    last_error = ?
                WHERE message_id = ?
                """,
                (error_count, retry_after, last_error, message_id),
            )
            self._conn.commit()

    def outbox_mark_dead(
        self,
        message_id: str,
        *,
        error_count: int,
        last_error: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE outbox
                SET status = 'dead',
                    error_count = ?,
                    retry_after = NULL,
                    last_error = ?
                WHERE message_id = ?
                """,
                (error_count, last_error, message_id),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
