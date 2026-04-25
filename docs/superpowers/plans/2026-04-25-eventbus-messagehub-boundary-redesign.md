# EventBus 与 MessageHub 边界重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前基于 `EventBus` hook 和 `model_events` 的消息设计重构为基于 `MessageEnvelope`、`WorldMessageReceiver`、`WorldMessageSender` 的显式边界架构，并支持 `world_id="*"` 广播、逐 world 投递状态和 world 级独立生命周期。

**Architecture:** 新增 `src/runtime/messaging/` 包，集中放置消息信封、存储、hub、processor、adapter 和 sender。`MessageHub` 仅负责 worker 级装配与生命周期；`InboxProcessor` 负责入站展开和逐 world 投递；`OutboxProcessor` 负责出站发送；world 侧通过 `EventBusMessageAdapter` 接收入站，通过 `WorldMessageSender` 显式发出外部消息。

**Tech Stack:** Python 3.13, pytest, asyncio, sqlite3, existing worker/channel/runtime infrastructure

---

## File Structure

### New Files

- `src/runtime/messaging/__init__.py`
  - 统一导出 `MessageEnvelope`、`MessageHub`、`WorldMessageReceiver`、`WorldMessageSender`、`EventBusMessageAdapter`
- `src/runtime/messaging/envelope.py`
  - `MessageEnvelope` dataclass
- `src/runtime/messaging/errors.py`
  - `RetryableDeliveryError` / `PermanentDeliveryError`
- `src/runtime/messaging/store.py`
  - 新的 `MessageStore` 抽象接口
- `src/runtime/messaging/send_result.py`
  - `SendResult` 枚举，从旧 `src/runtime/messaging.py` 迁入 package
- `src/runtime/messaging/sqlite_store.py`
  - 新 schema：`inbox` / `inbox_deliveries` / `outbox`
- `src/runtime/messaging/world_receiver.py`
  - `WorldMessageReceiver` protocol
- `src/runtime/messaging/world_sender.py`
  - `WorldMessageSender`
- `src/runtime/messaging/eventbus_adapter.py`
  - `EventBusMessageAdapter`
- `src/runtime/messaging/hub.py`
  - 新 `MessageHub`
- `src/runtime/messaging/inbox_processor.py`
  - 入站展开、逐 world 投递、retry/dead
- `src/runtime/messaging/outbox_processor.py`
  - 出站发送、retry/dead
- `tests/runtime/messaging/test_envelope.py`
- `tests/runtime/messaging/test_sqlite_store.py`
- `tests/runtime/messaging/test_world_sender.py`
- `tests/runtime/messaging/test_hub.py`
- `tests/runtime/messaging/test_inbox_processor.py`
- `tests/runtime/messaging/test_outbox_processor.py`
- `tests/runtime/messaging/test_eventbus_adapter.py`

### Modified Files

- `src/runtime/stores/base.py`
  - 删除旧 `MessageStore` 抽象，改为从 `src/runtime/messaging/store.py` re-export
- `src/runtime/event_bus.py`
  - 去掉仅为 `MessageHub` 服务的 hook 依赖
- `src/runtime/world_registry.py`
  - 为 bundle 创建 `message_receiver`
- `src/worker/channels/base.py`
  - 改为以 `MessageEnvelope` 作为 inbound / outbound 边界
- `src/worker/channels/jsonrpc_channel.py`
  - 改为发送/接收 `MessageEnvelope`
- `src/worker/manager.py`
  - 动态 `world.start` / `world.stop` 时正确注册和注销 world receiver
- `src/worker/cli/run_command.py`
  - 用新 `MessageHub` 装配 world receiver / sender
- `src/worker/cli/run_inline.py`
  - 用新 `MessageHub` 装配 world receiver / sender
- `tests/worker/channels/test_jsonrpc_channel.py`
- `tests/worker/test_manager.py`
- `tests/worker/cli/test_run_inline.py`

### Deleted Files

- `src/runtime/message_hub.py`
- `src/runtime/inbox_processor.py`
- `src/runtime/outbox_processor.py`
- `src/runtime/stores/sqlite_message_store.py`
- `src/runtime/message.py`
- `src/runtime/messaging.py`

### Compatibility Decision

本计划不保留旧路径兼容 shim。所有运行时代码和测试一次性切换到 `src/runtime/messaging/`，避免新旧实现并存导致职责回退。

## Task 1: 建立消息边界基础类型

**Files:**
- Create: `src/runtime/messaging/__init__.py`
- Create: `src/runtime/messaging/envelope.py`
- Create: `src/runtime/messaging/errors.py`
- Create: `src/runtime/messaging/world_receiver.py`
- Create: `src/runtime/messaging/world_sender.py`
- Create: `src/runtime/messaging/send_result.py`
- Create: `tests/runtime/messaging/test_envelope.py`
- Create: `tests/runtime/messaging/test_world_sender.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/runtime/messaging/test_envelope.py
from src.runtime.messaging.envelope import MessageEnvelope


def test_message_envelope_round_trips_dict_shape():
    envelope = MessageEnvelope(
        message_id="msg-1",
        world_id="factory-a",
        event_type="order.created",
        payload={"order_id": "O1001"},
        source="erp",
        scope="world",
        target=None,
        trace_id="trace-1",
        headers={"x-env": "test"},
    )

    assert envelope.message_id == "msg-1"
    assert envelope.world_id == "factory-a"
    assert envelope.source == "erp"
    assert envelope.headers == {"x-env": "test"}


def test_message_envelope_allows_explicit_broadcast_world():
    envelope = MessageEnvelope(
        message_id="msg-2",
        world_id="*",
        event_type="shift.changed",
        payload={"shift": "night"},
    )

    assert envelope.world_id == "*"
    assert envelope.scope == "world"
    assert envelope.target is None
```

```python
# tests/runtime/messaging/test_world_sender.py
from src.runtime.messaging import MessageEnvelope, WorldMessageSender


class _FakeHub:
    def __init__(self):
        self.seen = []

    def enqueue_outbound(self, envelope: MessageEnvelope) -> None:
        self.seen.append(envelope)


def test_world_message_sender_builds_envelope_and_enqueues():
    hub = _FakeHub()
    sender = WorldMessageSender(world_id="factory-a", hub=hub, source="world:factory-a")

    message_id = sender.send(
        "order.created",
        {"order_id": "O1001"},
        target_world_id="factory-b",
        target="robot-7",
        trace_id="trace-9",
        headers={"priority": "high"},
    )

    assert message_id
    assert len(hub.seen) == 1
    assert hub.seen[0].world_id == "factory-b"
    assert hub.seen[0].source == "world:factory-a"
    assert hub.seen[0].target == "robot-7"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/runtime/messaging/test_envelope.py tests/runtime/messaging/test_world_sender.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.runtime.messaging'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/messaging/envelope.py
from dataclasses import dataclass, field


@dataclass(slots=True)
class MessageEnvelope:
    message_id: str
    world_id: str
    event_type: str
    payload: dict
    source: str | None = None
    scope: str = "world"
    target: str | None = None
    trace_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
```

```python
# src/runtime/messaging/world_receiver.py
from typing import Protocol

from src.runtime.messaging.envelope import MessageEnvelope


class WorldMessageReceiver(Protocol):
    async def receive(self, envelope: MessageEnvelope) -> None:
        pass
```

```python
# src/runtime/messaging/errors.py
class RetryableDeliveryError(RuntimeError):
    pass


class PermanentDeliveryError(RuntimeError):
    pass
```

```python
# src/runtime/messaging/send_result.py
from enum import Enum


class SendResult(Enum):
    SUCCESS = "success"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"
```

```python
# src/runtime/messaging/world_sender.py
import uuid

from src.runtime.messaging.envelope import MessageEnvelope


class WorldMessageSender:
    def __init__(self, world_id: str, hub, source: str):
        self._world_id = world_id
        self._hub = hub
        self._source = source

    def bind_hub(self, hub) -> None:
        self._hub = hub

    def send(
        self,
        event_type: str,
        payload: dict,
        *,
        target_world_id: str,
        scope: str = "world",
        target: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        message_id = str(uuid.uuid4())
        envelope = MessageEnvelope(
            message_id=message_id,
            world_id=target_world_id,
            event_type=event_type,
            payload=payload,
            source=self._source,
            scope=scope,
            target=target,
            trace_id=trace_id,
            headers=headers or {},
        )
        self._hub.enqueue_outbound(envelope)
        return message_id
```

```python
# src/runtime/messaging/__init__.py
from src.runtime.messaging.envelope import MessageEnvelope
from src.runtime.messaging.errors import PermanentDeliveryError, RetryableDeliveryError
from src.runtime.messaging.send_result import SendResult
from src.runtime.messaging.world_receiver import WorldMessageReceiver
from src.runtime.messaging.world_sender import WorldMessageSender

__all__ = [
    "MessageEnvelope",
    "PermanentDeliveryError",
    "RetryableDeliveryError",
    "SendResult",
    "WorldMessageReceiver",
    "WorldMessageSender",
]
```

```bash
git rm src/runtime/messaging.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/runtime/messaging/test_envelope.py tests/runtime/messaging/test_world_sender.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/messaging/__init__.py src/runtime/messaging/envelope.py src/runtime/messaging/errors.py src/runtime/messaging/send_result.py src/runtime/messaging/world_receiver.py src/runtime/messaging/world_sender.py tests/runtime/messaging/test_envelope.py tests/runtime/messaging/test_world_sender.py
git rm src/runtime/messaging.py
git commit -m "feat: add messaging envelope and sender primitives"
```

## Task 2: 实现新的消息存储与 schema

**Files:**
- Create: `src/runtime/messaging/store.py`
- Create: `src/runtime/messaging/sqlite_store.py`
- Modify: `src/runtime/stores/base.py`
- Create: `tests/runtime/messaging/test_sqlite_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/runtime/messaging/test_sqlite_store.py
from src.runtime.messaging import MessageEnvelope
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


def _envelope(message_id: str, world_id: str = "factory-a") -> MessageEnvelope:
    return MessageEnvelope(
        message_id=message_id,
        world_id=world_id,
        event_type="order.created",
        payload={"order_id": message_id},
        source="erp",
    )


def test_inbox_append_and_expand_delivery(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-1"))
        pending = store.inbox_read_pending(limit=10)
        assert [m.message_id for m in pending] == ["msg-1"]

        store.inbox_create_deliveries("msg-1", ["factory-a"])
        deliveries = store.inbox_read_pending_deliveries(limit=10)
        assert [(d.message_id, d.target_world_id) for d in deliveries] == [("msg-1", "factory-a")]
    finally:
        store.close()


def test_broadcast_delivery_is_unique_per_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.inbox_append(_envelope("msg-2", world_id="*"))
        store.inbox_create_deliveries("msg-2", ["factory-a", "factory-b"])
        store.inbox_create_deliveries("msg-2", ["factory-a", "factory-b"])
        deliveries = store.inbox_read_pending_deliveries(limit=10)
        assert sorted((d.message_id, d.target_world_id) for d in deliveries) == [
            ("msg-2", "factory-a"),
            ("msg-2", "factory-b"),
        ]
    finally:
        store.close()


def test_outbox_append_and_mark_sent(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    try:
        store.outbox_append(_envelope("msg-3", world_id="factory-b"))
        pending = store.outbox_read_pending(limit=10)
        assert [m.message_id for m in pending] == ["msg-3"]

        store.outbox_mark_sent("msg-3")
        assert store.outbox_read_pending(limit=10) == []
    finally:
        store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/runtime/messaging/test_sqlite_store.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `src.runtime.messaging.sqlite_store`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/messaging/store.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.runtime.messaging.envelope import MessageEnvelope


@dataclass(slots=True)
class InboxDelivery:
    message_id: str
    target_world_id: str
    status: str
    error_count: int = 0
    retry_after: str | None = None
    last_error: str | None = None


class MessageStore(ABC):
    @abstractmethod
    def inbox_append(self, envelope: MessageEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_read_pending(self, limit: int) -> list[MessageEnvelope]:
        raise NotImplementedError

    @abstractmethod
    def inbox_load(self, message_id: str) -> MessageEnvelope:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_expanded(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_completed(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_failed(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_create_deliveries(self, message_id: str, world_ids: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_read_pending_deliveries(self, limit: int) -> list[InboxDelivery]:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_delivery_delivered(self, message_id: str, world_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_delivery_retry(self, message_id: str, world_id: str, *, error_count: int, retry_after: str | None, last_error: str | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_mark_delivery_dead(self, message_id: str, world_id: str, *, error_count: int, last_error: str | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def inbox_reconcile_statuses(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_append(self, envelope: MessageEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_read_pending(self, limit: int) -> list[MessageEnvelope]:
        raise NotImplementedError

    @abstractmethod
    def outbox_mark_sent(self, message_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_mark_retry(self, message_id: str, *, error_count: int, retry_after: str | None, last_error: str | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def outbox_mark_dead(self, message_id: str, *, error_count: int, last_error: str | None) -> None:
        raise NotImplementedError
```

```python
# src/runtime/messaging/sqlite_store.py
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
        self._conn = sqlite3.connect(os.path.join(store_dir, "messagebox.db"), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._lock = threading.Lock()
        self._ensure_schema()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS inbox (
            message_id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
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
        CREATE TABLE IF NOT EXISTS inbox_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            target_world_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_count INTEGER NOT NULL DEFAULT 0,
            retry_after TEXT,
            last_error TEXT,
            delivered_at TEXT,
            UNIQUE(message_id, target_world_id)
        );
        CREATE TABLE IF NOT EXISTS outbox (
            message_id TEXT PRIMARY KEY,
            world_id TEXT NOT NULL,
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
        """
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()

    def inbox_append(self, envelope: MessageEnvelope) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO inbox (
                    message_id, world_id, event_type, payload, source, scope, target, trace_id, headers, received_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    envelope.message_id,
                    envelope.world_id,
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
            SELECT message_id, world_id, event_type, payload, source, scope, target, trace_id, headers
            FROM inbox
            WHERE status = 'pending'
            ORDER BY received_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            MessageEnvelope(
                message_id=row[0],
                world_id=row[1],
                event_type=row[2],
                payload=json.loads(row[3]),
                source=row[4],
                scope=row[5],
                target=row[6],
                trace_id=row[7],
                headers=json.loads(row[8]),
            )
            for row in rows
        ]

    def inbox_load(self, message_id: str) -> MessageEnvelope:
        row = self._conn.execute(
            """
            SELECT message_id, world_id, event_type, payload, source, scope, target, trace_id, headers
            FROM inbox
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        return MessageEnvelope(
            message_id=row[0],
            world_id=row[1],
            event_type=row[2],
            payload=json.loads(row[3]),
            source=row[4],
            scope=row[5],
            target=row[6],
            trace_id=row[7],
            headers=json.loads(row[8]),
        )

    def inbox_mark_expanded(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE inbox SET status = 'expanded' WHERE message_id = ?", (message_id,))
            self._conn.commit()

    def inbox_mark_completed(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE inbox SET status = 'completed' WHERE message_id = ?", (message_id,))
            self._conn.commit()

    def inbox_mark_failed(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE inbox SET status = 'failed' WHERE message_id = ?", (message_id,))
            self._conn.commit()

    def inbox_create_deliveries(self, message_id: str, world_ids: list[str]) -> None:
        with self._lock:
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO inbox_deliveries (message_id, target_world_id, status)
                VALUES (?, ?, 'pending')
                """,
                [(message_id, world_id) for world_id in world_ids],
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
                message_id=row[0],
                target_world_id=row[1],
                status=row[2],
                error_count=row[3],
                retry_after=row[4],
                last_error=row[5],
            )
            for row in rows
        ]

    def inbox_mark_delivery_delivered(self, message_id: str, world_id: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'delivered', delivered_at = ?, retry_after = NULL, last_error = NULL
                WHERE message_id = ? AND target_world_id = ?
                """,
                (self._now(), message_id, world_id),
            )
            self._conn.commit()

    def inbox_mark_delivery_retry(self, message_id: str, world_id: str, *, error_count: int, retry_after: str | None, last_error: str | None) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'retry', error_count = ?, retry_after = ?, last_error = ?
                WHERE message_id = ? AND target_world_id = ?
                """,
                (error_count, retry_after, last_error, message_id, world_id),
            )
            self._conn.commit()

    def inbox_mark_delivery_dead(self, message_id: str, world_id: str, *, error_count: int, last_error: str | None) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE inbox_deliveries
                SET status = 'dead', error_count = ?, retry_after = NULL, last_error = ?
                WHERE message_id = ? AND target_world_id = ?
                """,
                (error_count, last_error, message_id, world_id),
            )
            self._conn.commit()

    def inbox_reconcile_statuses(self) -> None:
        with self._lock:
            message_ids = [
                row[0]
                for row in self._conn.execute("SELECT DISTINCT message_id FROM inbox_deliveries").fetchall()
            ]
            for message_id in message_ids:
                statuses = [
                    row[0]
                    for row in self._conn.execute(
                        "SELECT status FROM inbox_deliveries WHERE message_id = ?",
                        (message_id,),
                    ).fetchall()
                ]
                if statuses and all(status == "delivered" for status in statuses):
                    self._conn.execute("UPDATE inbox SET status = 'completed' WHERE message_id = ?", (message_id,))
                elif statuses and all(status in ("delivered", "dead", "failed") for status in statuses):
                    self._conn.execute("UPDATE inbox SET status = 'failed' WHERE message_id = ?", (message_id,))
            self._conn.commit()

    def outbox_append(self, envelope: MessageEnvelope) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO outbox (
                    message_id, world_id, event_type, payload, source, scope, target, trace_id, headers, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    envelope.message_id,
                    envelope.world_id,
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
            SELECT message_id, world_id, event_type, payload, source, scope, target, trace_id, headers
            FROM outbox
            WHERE status IN ('pending', 'retry')
              AND (retry_after IS NULL OR retry_after <= ?)
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (self._now(), limit),
        ).fetchall()
        return [
            MessageEnvelope(
                message_id=row[0],
                world_id=row[1],
                event_type=row[2],
                payload=json.loads(row[3]),
                source=row[4],
                scope=row[5],
                target=row[6],
                trace_id=row[7],
                headers=json.loads(row[8]),
            )
            for row in rows
        ]

    def outbox_mark_sent(self, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE outbox SET status = 'sent', sent_at = ?, retry_after = NULL, last_error = NULL WHERE message_id = ?",
                (self._now(), message_id),
            )
            self._conn.commit()

    def outbox_mark_retry(self, message_id: str, *, error_count: int, retry_after: str | None, last_error: str | None) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE outbox
                SET status = 'retry', error_count = ?, retry_after = ?, last_error = ?
                WHERE message_id = ?
                """,
                (error_count, retry_after, last_error, message_id),
            )
            self._conn.commit()

    def outbox_mark_dead(self, message_id: str, *, error_count: int, last_error: str | None) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE outbox
                SET status = 'dead', error_count = ?, retry_after = NULL, last_error = ?
                WHERE message_id = ?
                """,
                (error_count, last_error, message_id),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
```

```python
# src/runtime/stores/base.py
from src.runtime.messaging.store import MessageStore  # re-export the new worker-level message store
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/runtime/messaging/test_sqlite_store.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/messaging/store.py src/runtime/messaging/sqlite_store.py src/runtime/stores/base.py tests/runtime/messaging/test_sqlite_store.py
git commit -m "feat: add worker-level message store schema"
```

## Task 3: 实现 hub、processor 与 EventBus 适配器

**Files:**
- Create: `src/runtime/messaging/hub.py`
- Create: `src/runtime/messaging/inbox_processor.py`
- Create: `src/runtime/messaging/outbox_processor.py`
- Create: `src/runtime/messaging/eventbus_adapter.py`
- Modify: `src/runtime/messaging/__init__.py`
- Create: `tests/runtime/messaging/test_eventbus_adapter.py`
- Create: `tests/runtime/messaging/test_hub.py`
- Create: `tests/runtime/messaging/test_inbox_processor.py`
- Create: `tests/runtime/messaging/test_outbox_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/runtime/messaging/test_eventbus_adapter.py
import asyncio

import pytest

from src.runtime.event_bus import EventBus
from src.runtime.messaging import EventBusMessageAdapter, MessageEnvelope


@pytest.mark.anyio
async def test_eventbus_message_adapter_publishes_to_event_bus():
    bus = EventBus()
    seen = []
    event = asyncio.Event()

    bus.register("inst-1", "world", "order.created", lambda t, p, s: (seen.append((t, p, s)), event.set()))

    adapter = EventBusMessageAdapter(bus)
    await adapter.receive(
        MessageEnvelope(
            message_id="msg-1",
            world_id="factory-a",
            event_type="order.created",
            payload={"order_id": "O1001"},
            source="erp",
        )
    )

    await asyncio.wait_for(event.wait(), timeout=1.0)
    assert seen == [("order.created", {"order_id": "O1001"}, "erp")]
```

```python
# tests/runtime/messaging/test_hub.py
from src.runtime.messaging import MessageEnvelope, MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


def test_hub_registers_and_unregisters_world(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    hub = MessageHub(message_store=store, channel=None)

    class _Receiver:
        async def receive(self, envelope):
            raise AssertionError("should not be called")

    hub.register_world("factory-a", _Receiver())
    assert set(hub.registered_worlds()) == {"factory-a"}

    hub.unregister_world("factory-a")
    assert hub.registered_worlds() == []
```

```python
# tests/runtime/messaging/test_inbox_processor.py
import pytest

from src.runtime.messaging import MessageEnvelope, MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


@pytest.mark.anyio
async def test_inbox_processor_expands_broadcast_and_delivers(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    seen = []

    class _Receiver:
        def __init__(self, world_id):
            self._world_id = world_id

        async def receive(self, envelope):
            seen.append((self._world_id, envelope.message_id))

    hub = MessageHub(message_store=store, channel=None, poll_interval=0.01)
    hub.register_world("factory-a", _Receiver("factory-a"))
    hub.register_world("factory-b", _Receiver("factory-b"))
    hub.on_inbound(MessageEnvelope(message_id="msg-1", world_id="*", event_type="shift.changed", payload={"shift": "night"}))

    await hub.start()
    try:
        import asyncio
        await asyncio.sleep(0.1)
    finally:
        await hub.stop()

    assert sorted(seen) == [("factory-a", "msg-1"), ("factory-b", "msg-1")]
```

```python
# tests/runtime/messaging/test_outbox_processor.py
import asyncio

import pytest

from src.runtime.messaging import MessageEnvelope, MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore
from src.runtime.messaging import SendResult


class _FakeChannel:
    def __init__(self):
        self.sent = []
        self.sent_event = asyncio.Event()

    async def start(self, inbound_callback):
        self._callback = inbound_callback

    async def send(self, envelope):
        self.sent.append(envelope.message_id)
        self.sent_event.set()
        return SendResult.SUCCESS

    async def stop(self):
        return None

    def is_ready(self):
        return True


@pytest.mark.anyio
async def test_outbox_processor_sends_enqueued_envelope(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    channel = _FakeChannel()
    hub = MessageHub(message_store=store, channel=channel, poll_interval=0.01)

    hub.enqueue_outbound(MessageEnvelope(message_id="msg-9", world_id="factory-b", event_type="order.created", payload={"order_id": "O9"}))

    await hub.start()
    try:
        await asyncio.wait_for(channel.sent_event.wait(), timeout=1.0)
    finally:
        await hub.stop()

    assert channel.sent == ["msg-9"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/runtime/messaging/test_eventbus_adapter.py tests/runtime/messaging/test_hub.py tests/runtime/messaging/test_inbox_processor.py tests/runtime/messaging/test_outbox_processor.py -v
```

Expected: FAIL with missing `MessageHub` / `EventBusMessageAdapter` symbols

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/messaging/eventbus_adapter.py
from src.runtime.event_bus import EventBus
from src.runtime.messaging.envelope import MessageEnvelope
from src.runtime.messaging.world_receiver import WorldMessageReceiver


class EventBusMessageAdapter(WorldMessageReceiver):
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    async def receive(self, envelope: MessageEnvelope) -> None:
        self._event_bus.publish(
            envelope.event_type,
            envelope.payload,
            source=envelope.source or "external",
            scope=envelope.scope,
            target=envelope.target,
        )
```

```python
# src/runtime/messaging/hub.py
import threading

from src.runtime.messaging.inbox_processor import InboxProcessor
from src.runtime.messaging.outbox_processor import OutboxProcessor


class MessageHub:
    def __init__(self, message_store, channel, poll_interval: float = 1.0):
        self._store = message_store
        self._channel = channel
        self._lock = threading.RLock()
        self._receivers = {}
        self._inbox_processor = InboxProcessor(self, poll_interval=poll_interval)
        self._outbox_processor = OutboxProcessor(self, poll_interval=poll_interval)

    def register_world(self, world_id: str, receiver) -> None:
        with self._lock:
            self._receivers[world_id] = receiver

    def unregister_world(self, world_id: str) -> None:
        with self._lock:
            self._receivers.pop(world_id, None)

    def get_receiver(self, world_id: str):
        with self._lock:
            return self._receivers.get(world_id)

    def registered_worlds(self) -> list[str]:
        with self._lock:
            return sorted(self._receivers.keys())

    def on_inbound(self, envelope) -> None:
        self._store.inbox_append(envelope)

    def enqueue_outbound(self, envelope) -> None:
        self._store.outbox_append(envelope)

    async def start(self) -> None:
        if self._channel is not None:
            await self._channel.start(self.on_inbound)
        self._inbox_processor.start()
        self._outbox_processor.start()

    async def stop(self) -> None:
        await self._inbox_processor.stop()
        await self._outbox_processor.stop()
        if self._channel is not None:
            await self._channel.stop()
```

```python
# src/runtime/messaging/inbox_processor.py
import asyncio
from datetime import datetime, timedelta, timezone

from src.runtime.messaging.errors import PermanentDeliveryError, RetryableDeliveryError


class InboxProcessor:
    def __init__(self, hub, poll_interval: float = 1.0, batch_size: int = 100, max_retries: int = 10):
        self._hub = hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._task = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            for envelope in self._hub._store.inbox_read_pending(self._batch_size):
                target_worlds = (
                    self._hub.registered_worlds()
                    if envelope.world_id == "*"
                    else [envelope.world_id]
                )
                self._hub._store.inbox_create_deliveries(envelope.message_id, target_worlds)
                self._hub._store.inbox_mark_expanded(envelope.message_id)

            deliveries = self._hub._store.inbox_read_pending_deliveries(self._batch_size)
            for delivery in deliveries:
                receiver = self._hub.get_receiver(delivery.target_world_id)
                if receiver is None:
                    retry_after = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
                    self._hub._store.inbox_mark_delivery_retry(
                        delivery.message_id,
                        delivery.target_world_id,
                        error_count=delivery.error_count + 1,
                        retry_after=retry_after,
                        last_error="world receiver unavailable",
                    )
                    continue
                envelope = self._hub._store.inbox_load(delivery.message_id)
                try:
                    await receiver.receive(envelope)
                    self._hub._store.inbox_mark_delivery_delivered(delivery.message_id, delivery.target_world_id)
                except RetryableDeliveryError as exc:
                    retry_after = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
                    self._hub._store.inbox_mark_delivery_retry(
                        delivery.message_id,
                        delivery.target_world_id,
                        error_count=delivery.error_count + 1,
                        retry_after=retry_after,
                        last_error=str(exc),
                    )
                except PermanentDeliveryError as exc:
                    self._hub._store.inbox_mark_delivery_dead(
                        delivery.message_id,
                        delivery.target_world_id,
                        error_count=delivery.error_count + 1,
                        last_error=str(exc),
                    )

            self._hub._store.inbox_reconcile_statuses()
            await asyncio.sleep(self._poll_interval)
```

```python
# src/runtime/messaging/outbox_processor.py
import asyncio
from datetime import datetime, timedelta, timezone

from src.runtime.messaging import SendResult


class OutboxProcessor:
    def __init__(self, hub, poll_interval: float = 1.0, batch_size: int = 100, max_retries: int = 10):
        self._hub = hub
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._task = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._hub._channel is None:
                await asyncio.sleep(self._poll_interval)
                continue
            for envelope in self._hub._store.outbox_read_pending(self._batch_size):
                result = await self._hub._channel.send(envelope)
                if result == SendResult.SUCCESS:
                    self._hub._store.outbox_mark_sent(envelope.message_id)
                elif result == SendResult.RETRYABLE:
                    retry_after = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
                    self._hub._store.outbox_mark_retry(
                        envelope.message_id,
                        error_count=1,
                        retry_after=retry_after,
                        last_error="retryable failure",
                    )
                else:
                    self._hub._store.outbox_mark_dead(
                        envelope.message_id,
                        error_count=self._max_retries,
                        last_error="permanent failure",
                    )
            await asyncio.sleep(self._poll_interval)
```

```python
# src/runtime/messaging/__init__.py
from src.runtime.messaging.eventbus_adapter import EventBusMessageAdapter
from src.runtime.messaging.hub import MessageHub
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/runtime/messaging/test_eventbus_adapter.py tests/runtime/messaging/test_hub.py tests/runtime/messaging/test_inbox_processor.py tests/runtime/messaging/test_outbox_processor.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/messaging/__init__.py src/runtime/messaging/eventbus_adapter.py src/runtime/messaging/hub.py src/runtime/messaging/inbox_processor.py src/runtime/messaging/outbox_processor.py tests/runtime/messaging/test_eventbus_adapter.py tests/runtime/messaging/test_hub.py tests/runtime/messaging/test_inbox_processor.py tests/runtime/messaging/test_outbox_processor.py
git commit -m "feat: add messaging hub processors and event bus adapter"
```

## Task 4: 切换 channel API 到 MessageEnvelope

**Files:**
- Modify: `src/worker/channels/base.py`
- Modify: `src/worker/channels/jsonrpc_channel.py`
- Modify: `tests/worker/channels/test_jsonrpc_channel.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/worker/channels/test_jsonrpc_channel.py
import asyncio
import json

import pytest
import websockets

from src.runtime.messaging import MessageEnvelope, SendResult
from src.worker.channels.jsonrpc_channel import JsonRpcChannel


@pytest.mark.anyio
async def test_jsonrpc_channel_send_uses_message_envelope():
    received = []

    async def handler(websocket):
        async for raw in websocket:
            message = json.loads(raw)
            received.append(message)
            await websocket.send(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"acked": True}}))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    channel = JsonRpcChannel(f"ws://127.0.0.1:{port}")
    await channel.start(lambda envelope: None)

    for _ in range(20):
        if channel.is_ready():
            break
        await asyncio.sleep(0.05)

    result = await channel.send(
        MessageEnvelope(
            message_id="msg-1",
            world_id="factory-b",
            event_type="order.created",
            payload={"order_id": "O1"},
            source="world:factory-a",
        )
    )

    await channel.stop()
    server.close()
    await server.wait_closed()

    assert result == SendResult.SUCCESS
    assert received[0]["params"]["world_id"] == "factory-b"
    assert received[0]["params"]["message_id"] == "msg-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/worker/channels/test_jsonrpc_channel.py -v
```

Expected: FAIL because `JsonRpcChannel.send()` still expects split fields

- [ ] **Step 3: Write minimal implementation**

```python
# src/worker/channels/base.py
from abc import ABC, abstractmethod
from typing import Callable

from src.runtime.messaging import MessageEnvelope, SendResult


class Channel(ABC):
    @abstractmethod
    async def start(self, inbound_callback: Callable[[MessageEnvelope], None]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, envelope: MessageEnvelope) -> SendResult:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_ready(self) -> bool:
        raise NotImplementedError
```

```python
# src/worker/channels/jsonrpc_channel.py
async def send(self, envelope: MessageEnvelope) -> SendResult:
    if not self._ready or self._conn is None:
        return SendResult.RETRYABLE
    req_id = str(uuid.uuid4())
    message = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "messageHub.publish",
        "params": {
            "message_id": envelope.message_id,
            "world_id": envelope.world_id,
            "event_type": envelope.event_type,
            "payload": envelope.payload,
            "source": envelope.source,
            "scope": envelope.scope,
            "target": envelope.target,
            "trace_id": envelope.trace_id,
            "headers": envelope.headers,
        },
    }
    result = await self._send_and_wait(req_id, message)
    return SendResult.SUCCESS if result else SendResult.RETRYABLE

async def on_external_event(params, _req_id):
    if self._inbound_callback is not None:
        self._inbound_callback(
            MessageEnvelope(
                message_id=params["message_id"],
                world_id=params["world_id"],
                event_type=params["event_type"],
                payload=params.get("payload", {}),
                source=params.get("source"),
                scope=params.get("scope", "world"),
                target=params.get("target"),
                trace_id=params.get("trace_id"),
                headers=params.get("headers") or {},
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/worker/channels/test_jsonrpc_channel.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/channels/base.py src/worker/channels/jsonrpc_channel.py tests/worker/channels/test_jsonrpc_channel.py
git commit -m "refactor: switch channel API to message envelopes"
```

## Task 5: 集成 world / worker 生命周期

**Files:**
- Modify: `src/runtime/world_registry.py`
- Modify: `src/worker/manager.py`
- Modify: `src/worker/cli/run_command.py`
- Modify: `src/worker/cli/run_inline.py`
- Modify: `tests/worker/test_manager.py`
- Modify: `tests/worker/cli/test_run_inline.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/worker/test_manager.py
import tempfile

import pytest

from src.runtime.world_registry import WorldRegistry
from src.worker.manager import WorkerManager


@pytest.mark.anyio
async def test_worker_manager_world_start_registers_receiver_and_sender():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)
        hub = wm.build_message_hub(worker_dir=tmp, channel=None)

        result = await wm.handle_command("world.start", {"world_id": "factory-01", "world_dir": f"{tmp}/factory-01"})

        assert result["status"] == "started"
        assert "factory-01" in hub.registered_worlds()
        assert wm.worlds["factory-01"]["message_sender"] is not None
```

```python
# tests/worker/cli/test_run_inline.py
import os
import tempfile

from src.runtime.world_registry import WorldRegistry
from src.worker.manager import WorkerManager


def test_run_inline_registers_message_receivers_for_all_worlds():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")
        reg.create_world("factory-02")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)
        message_hub = wm.build_message_hub(worker_dir=os.path.join(tmp, "messagebox"), channel=None)

        bundle1 = wm.worlds["factory-01"]
        bundle2 = wm.worlds["factory-02"]

        assert sorted(message_hub.registered_worlds()) == ["factory-01", "factory-02"]
        assert bundle1["message_receiver"] is not None
        assert bundle2["message_sender"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/worker/test_manager.py tests/worker/cli/test_run_inline.py -v
```

Expected: FAIL because `WorkerManager` has no `build_message_hub()` and bundles lack receiver/sender

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/world_registry.py
from src.runtime.messaging import EventBusMessageAdapter, WorldMessageSender

bus = bus_reg.get_or_create(world_id)
message_receiver = EventBusMessageAdapter(bus)
message_sender = WorldMessageSender(world_id=world_id, hub=None, source=f"world:{world_id}")

bundle = {
    "world_id": world_id,
    "world_yaml": world_yaml,
    "store": store,
    "event_bus_registry": bus_reg,
    "instance_manager": im,
    "scene_manager": scene_mgr,
    "state_manager": state_mgr,
    "metric_store": metric_store,
    "world_state": world_state,
    "lock": world_lock,
    "alarm_manager": alarm_manager,
    "_registry": self,
    "force_stop_on_shutdown": False,
    "message_receiver": message_receiver,
    "message_sender": message_sender,
}
```

```python
# src/worker/manager.py
from src.runtime.messaging import MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore

class WorkerManager:
    def build_message_hub(self, worker_dir: str, channel) -> MessageHub:
        store = SQLiteMessageStore(worker_dir)
        hub = MessageHub(store, channel, poll_interval=0.05)
        for world_id, bundle in self.worlds.items():
            hub.register_world(world_id, bundle["message_receiver"])
            bundle["message_sender"].bind_hub(hub)
            bundle["message_hub"] = hub
        self._message_hub = hub
        return hub
```

```python
# src/worker/cli/run_command.py / src/worker/cli/run_inline.py
message_hub = worker_manager.build_message_hub(worker_dir=worker_dir, channel=channel)
await message_hub.start()
```

```python
# src/worker/manager.py in handle_command("world.start")
new_bundle = await asyncio.to_thread(registry.load_world, world_id)
self.worlds[world_id] = new_bundle
if getattr(self, "_message_hub", None) is not None:
    self._message_hub.register_world(world_id, new_bundle["message_receiver"])
    new_bundle["message_sender"].bind_hub(self._message_hub)
    new_bundle["message_hub"] = self._message_hub
```

```python
# src/worker/manager.py in _graceful_shutdown / unload_world
if getattr(self, "_message_hub", None) is not None:
    self._message_hub.unregister_world(world_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/worker/test_manager.py tests/worker/cli/test_run_inline.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/world_registry.py src/worker/manager.py src/worker/cli/run_command.py src/worker/cli/run_inline.py tests/worker/test_manager.py tests/worker/cli/test_run_inline.py
git commit -m "feat: wire world message receivers and senders into worker lifecycle"
```

## Task 6: 删除旧耦合并完成回归

**Files:**
- Modify: `src/runtime/event_bus.py`
- Delete: `src/runtime/message_hub.py`
- Delete: `src/runtime/inbox_processor.py`
- Delete: `src/runtime/outbox_processor.py`
- Delete: `src/runtime/stores/sqlite_message_store.py`
- Delete: `src/runtime/message.py`
- Modify: `tests/runtime/test_event_bus.py`
- Modify: `tests/runtime/test_message_hub.py`
- Modify: `tests/runtime/test_outbox_processor.py`

- [ ] **Step 1: Write the failing regression tests**

```python
# tests/runtime/test_event_bus.py
from src.runtime.event_bus import EventBus


def test_event_bus_publish_does_not_require_message_hub_hook():
    bus = EventBus()
    seen = []
    bus.register("inst-1", "world", "local.event", lambda t, p, s: seen.append((t, p, s)))

    bus.publish("local.event", {"ok": True}, "tester", "world")

    assert seen == [("local.event", {"ok": True}, "tester")]
```

```python
# tests/runtime/messaging/test_hub.py
import pytest

from src.runtime.messaging import MessageEnvelope, MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore


@pytest.mark.anyio
async def test_stopping_one_world_does_not_stop_shared_message_hub(tmp_path):
    store = SQLiteMessageStore(str(tmp_path))
    hub = MessageHub(store, channel=None, poll_interval=0.01)

    class _Receiver:
        async def receive(self, envelope):
            return None

    hub.register_world("factory-a", _Receiver())
    hub.register_world("factory-b", _Receiver())

    await hub.start()
    hub.unregister_world("factory-a")

    assert hub.registered_worlds() == ["factory-b"]
    await hub.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/runtime/test_event_bus.py tests/runtime/messaging/test_hub.py -v
```

Expected: FAIL until old imports and old lifecycle assumptions are removed

- [ ] **Step 3: Write minimal cleanup implementation**

```python
# src/runtime/event_bus.py
import logging
import threading

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, str, callable]]] = {}
        self._lock = threading.RLock()

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable):
        with self._lock:
            self._subscribers.setdefault(event_type, []).append((instance_id, scope, handler))

    def unregister(self, instance_id: str, event_type: str | None = None):
        with self._lock:
            if event_type is not None:
                self._subscribers[event_type] = [
                    (iid, sc, h)
                    for iid, sc, h in self._subscribers.get(event_type, [])
                    if iid != instance_id
                ]
                return
            for et in list(self._subscribers.keys()):
                self._subscribers[et] = [
                    (iid, sc, h) for iid, sc, h in self._subscribers[et] if iid != instance_id
                ]

    def publish(self, event_type: str, payload: dict, source: str, scope: str, target: str | None = None):
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for instance_id, inst_scope, handler in handlers:
            if target and instance_id != target:
                continue
            if scope != "world" and inst_scope != scope:
                continue
            try:
                handler(event_type, payload, source)
            except Exception:
                logger.exception("Handler failed for instance %s on event %s", instance_id, event_type)
```

```bash
rm src/runtime/message_hub.py
rm src/runtime/inbox_processor.py
rm src/runtime/outbox_processor.py
rm src/runtime/stores/sqlite_message_store.py
rm src/runtime/message.py
rm src/runtime/messaging.py
```

Update all remaining imports from:

```python
from src.runtime.message_hub import MessageHub
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
```

to:

```python
from src.runtime.messaging import MessageHub
from src.runtime.messaging.sqlite_store import SQLiteMessageStore
```

- [ ] **Step 4: Run full regression suite**

Run:

```bash
pytest tests/runtime/messaging tests/runtime/test_event_bus.py tests/worker/channels/test_jsonrpc_channel.py tests/worker/test_manager.py tests/worker/cli/test_run_inline.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/event_bus.py src/runtime/messaging src/runtime/stores/base.py src/runtime/world_registry.py src/worker/channels/base.py src/worker/channels/jsonrpc_channel.py src/worker/manager.py src/worker/cli/run_command.py src/worker/cli/run_inline.py tests/runtime/messaging tests/runtime/test_event_bus.py tests/worker/channels/test_jsonrpc_channel.py tests/worker/test_manager.py tests/worker/cli/test_run_inline.py
git rm src/runtime/message_hub.py src/runtime/inbox_processor.py src/runtime/outbox_processor.py src/runtime/stores/sqlite_message_store.py src/runtime/message.py src/runtime/messaging.py
git commit -m "refactor: separate world event bus from worker messaging plane"
```

## Self-Review Checklist

- Spec coverage:
  - `MessageEnvelope` 和显式 `world_id`：Task 1
  - `MessageHub` 仅做装配：Task 3
  - `InboxProcessor` 执行广播和逐 world delivery：Task 3
  - `OutboxProcessor` 执行发送：Task 3
  - `world_id="*"` 广播与 `inbox_deliveries`：Task 2 + Task 3
  - `WorldMessageReceiver` / `WorldMessageSender`：Task 1 + Task 5
  - world 生命周期与 shared hub 解耦：Task 5 + Task 6
  - 删除旧 hook 和 `model_events` 路径：Task 6

- Placeholder scan:
  - 本计划中不使用 `TODO`、`TBD`、`implement later`、`similar to Task N`

- Type consistency:
  - 入站 / 出站统一使用 `MessageEnvelope`
  - `source` / `target` 均为 `str | None`
  - `WorldMessageReceiver.receive(envelope)` 和 `Channel.send(envelope)` 都以信封为唯一参数
