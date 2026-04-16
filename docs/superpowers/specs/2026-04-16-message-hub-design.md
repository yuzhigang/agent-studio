# MessageHub 外部消息统一网关设计文档

> 版本：v1.0  
> 日期：2026-04-16

---

## 1. 背景与目标

当前 `agent-studio` 的 `EventBus` 负责 instance 之间的内部事件分发，但外部事件（来自 RabbitMQ、MQTT 等）的接入和 instance 产生的事件向外部系统的发送缺乏统一的抽象层。

本设计目标：

1. 建立一个统一的**外部消息网关（MessageHub）**，负责所有"跨边界"消息的可靠收发。
2. 保留现有 `EventBus` 处理纯内部事件，两者通过清晰接口解耦。
3. 为 Runtime 进程崩溃/重启场景提供消息持久化保障，不依赖特定 MQ 的重试机制。
4. 第一批实现支持 **RabbitMQ**，其他协议通过 Adapter 接口预留扩展。

---

## 2. 核心设计原则

- **Runtime 不知道 MessageHub**：业务代码和 behavior 脚本只调用 `EventRouter.publish()`，与从前完全一致。
- **MessageHub 不执行业务逻辑**：它只负责消息的可靠收发，不运行 behavior。
- **`messagebox.db` 独立存储**：每个 Project 拥有独立的 `messagebox.db`，与 `runtime.db` 解耦，由 Supervisor（MessageHub）和 Runtime 分别访问，不受 `.lock` 文件锁影响。
- **Push + Inbox 兜底**：Runtime 在线时消息实时推送；断连/崩溃时消息安全积压在 inbox，重连后通过 `syncInbox` 恢复。

---

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Supervisor Process                                │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐     │
│  │  HTTP API       │    │    MessageHub   │◄──►│  RabbitMQ Adapter   │     │
│  │  (mgmt plane)   │    │                 │    │  (extensible)       │     │
│  └────────┬────────┘    │  - inbox/outbox │    └─────────────────────┘     │
│           │             │  - push/sync    │                                │
│           ▼             │  - adapter mgmt │                                │
│  ┌─────────────────┐    └────────┬────────┘                                │
│  │  WebSocket GW   │             │                                         │
│  │  (clients)      │             │                                         │
│  └─────────────────┘             ▼                                         │
│                        ┌─────────────────┐                                 │
│                        │ messagebox.db   │  (per project, independent)    │
│                        │  - inbox table  │                                │
│                        │  - outbox table │                                │
│                        └─────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
              ▲                              │
              │ WebSocket JSON-RPC           │ WebSocket JSON-RPC
              │                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ProjectRuntime Process                              │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐     │
│  │  EventRouter    │───►│    EventBus     │◄──►│  InstanceManager    │     │
│  │  (publish入口)   │    │  (内部订阅分发)  │    │  (instance行为执行)  │     │
│  │                 │    └─────────────────┘    └─────────────────────┘     │
│  │  - 写 event log │                                                        │
│  │  - 写 outbox    │◄────────────────────────────────────────────┐         │
│  │  - 内部 publish  │                                            │         │
│  └─────────────────┘                                            │         │
│           ▲                                                     │         │
│           │ periodic sync / push                                │         │
│  ┌─────────────────┐                                            │         │
│  │ OutboxProcessor │────────────────────────────────────────────┘         │
│  │  (轻量线程)      │     扫描 outbox → 批量 RPC 到 MessageHub → 收到 ack 删除│
│  └─────────────────┘                                                      │
│                                                                             │
│  ┌─────────────────┐                                                       │
│  │  InboxHandler   │     处理 MessageHub push 或 sync 拉取的消息           │
│  │                 │     调用 EventRouter.publish() 注入内部 EventBus      │
│  └─────────────────┘                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据结构与存储 Schema

### 4.1 `messagebox.db`（独立 SQLite）

```sql
-- 收件箱：外部消息进入后先落地
CREATE TABLE inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence INTEGER NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    source TEXT,
    scope TEXT DEFAULT 'project',
    target TEXT,
    received_at TEXT NOT NULL,
    delivered_at TEXT,
    acked_at TEXT
);

-- 发件箱：需要外发的事件
CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence INTEGER NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    target TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    error_count INTEGER DEFAULT 0
);

-- 序列号管理
CREATE TABLE sequences (
    name TEXT PRIMARY KEY,
    value INTEGER DEFAULT 0
);

-- 查询优化索引
CREATE INDEX idx_inbox_sequence ON inbox(sequence);
CREATE INDEX idx_outbox_sequence ON outbox(sequence);
CREATE INDEX idx_outbox_published_at ON outbox(published_at, error_count);
```

> **并发提示**：`messagebox.db` 由 Supervisor 和 Runtime 同时读写，建议在 `MessageStore` 连接初始化时启用 SQLite WAL 模式并配置 busy-timeout，以避免写冲突。`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`

### 4.2 序列号生成逻辑

```python
def next_sequence(name: str) -> int:
    with transaction():
        cursor.execute(
            "INSERT INTO sequences(name, value) VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1 "
            "RETURNING value",
            (name,)
        )
        return cursor.fetchone()[0]
```

- `inbox` 和 `outbox` 使用独立的序列号空间（`name = 'inbox'` / `'outbox'`）。
- 序列号单调递增，是幂等和断点续传的核心依据。

---

## 5. 配置来源

### 5.1 Model 事件定义（能力声明）

Agent Model 定义事件是否具备外发能力：

```yaml
events:
  order.created:
    external: true
    schema:
      type: object
      properties:
        orderId: { type: string }
```

### 5.2 `project.yaml`（部署配置）

Project 部署层面配置"发到哪里"：

```yaml
project_id: factory-01
name: Factory 01
config:
  message_hub:
    adapter: rabbitmq
    rabbitmq:
      host: localhost
      port: 5672
      exchange: factory.events
      routing_key: "#{event_type}"
```

- Runtime 启动时读取 `message_hub` 配置，初始化 `OutboxProcessor`。
- MessageHub 读取同一配置，启动 RabbitMQ Consumer 和 Producer。

---

## 6. 组件接口

### 6.1 Runtime 侧：`EventRouter`

`EventRouter` 是 `EventBus` 的代理扩展层，接口保持与现有 `PersistentEventBus` 兼容：

```python
class EventRouter:
    def __init__(
        self,
        bus: EventBus,
        event_log_store: EventLogStore | None,
        message_store: MessageStore,
        model_events: dict[str, dict],
    ):
        ...

    def publish(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        # 1. 内部发布
        self._bus.publish(event_type, payload, source, scope, target)
        # 2. 写审计日志
        if persist and self._log_store:
            self._log_store.append(...)
        # 3. 外发到 outbox
        if self._is_external(event_type):
            self._message_store.outbox_enqueue(...)
```

### 6.2 Runtime 侧：`OutboxProcessor`

轻量守护线程，负责把 `outbox` 中的消息批量推送到 MessageHub：

```python
class OutboxProcessor:
    def __init__(self, message_store: MessageStore, rpc_client: RuntimeRpcClient):
        ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
```

处理流程：
1. 每 1s（可配置）扫描 `outbox` 表，读取未发送记录（`published_at IS NULL AND error_count < max_retries`）。
2. 组装 `publishBatch` RPC 调用，发送到 MessageHub。
3. 收到 ack 的 sequence 列表后，删除对应记录。
4. 未 ack 的记录等待下次重试，错误计数递增。
5. 超过 `max_retries`（默认 10 次）的记录不再自动重试，保留在 outbox 中供运维排查，或后续通过死信队列（DLQ）机制处理。

### 6.3 Runtime 侧：`InboxHandler`

处理来自 MessageHub 的外部事件推送：

```python
class InboxHandler:
    def __init__(self, event_router: EventRouter):
        self._router = event_router
        self._last_delivered_sequence = 0

    def on_external_event(
        self,
        event_type: str,
        payload: dict,
        source: str,
        sequence: int,
        scope: str = "project",
        target: str | None = None,
    ):
        if sequence <= self._last_delivered_sequence:
            return  # 幂等：已处理过
        self._router.publish(
            event_type=event_type,
            payload=payload,
            source=source,
            scope=scope,
            target=target,
            persist=False,  # 防止循环写入 outbox
        )
        self._last_delivered_sequence = sequence
```

### 6.4 Supervisor 侧：`MessageHub`

Supervisor 进程内部模块，管理每个 Project 的消息收发：

```python
class MessageHub:
    def __init__(self, base_dir: str, adapter_factory: AdapterFactory):
        ...

    def register_project(self, project_id: str, config: dict) -> None:
        """加载 messagebox.db，启动对应 adapter。"""

    def unregister_project(self, project_id: str) -> None:
        """关闭 adapter，释放资源。"""

    def on_outbox_batch(
        self, project_id: str, batch: list[OutboxRecord]
    ) -> list[int]:
        """Runtime 推送 outbox 批次，返回成功发送的 sequence 列表。"""

    def sync_inbox(
        self, project_id: str, last_sequence: int, limit: int
    ) -> list[InboxRecord]:
        """Runtime 拉取从 last_sequence 之后的 inbox 消息。"""
```

### 6.5 Adapter 抽象基类

```python
class MessageAdapter(ABC):
    @abstractmethod
    def start(
        self,
        inbound_callback: Callable[[str, dict, str, int], None],
        config: dict,
    ) -> None: ...

    @abstractmethod
    def publish(self, event_type: str, payload: dict, config: dict) -> bool: ...

    @abstractmethod
    def stop(self) -> None: ...
```

- `inbound_callback` 的签名是 `(event_type, payload, source, sequence) -> None`。
- `publish` 返回 `bool` 表示单条发送是否成功。在 `MessageHub.on_outbox_batch` 中，如果 `adapter.publish` 返回 `False`，则该批次中对应记录视为未 ack，由 `OutboxProcessor` 周期性重试。

- `RabbitMQAdapter` 作为第一个实现。
- 未来可扩展 `MQTTAdapter`、`KafkaAdapter`、`WebhookAdapter` 等。

---

## 7. Runtime ↔ MessageHub 通信协议

在现有 WebSocket JSON-RPC 2.0 通道上新增以下方法：

### 7.1 Request/Response

| 方法 | 方向 | 参数 | 返回值 |
|---|---|---|---|
| `messageHub.publishBatch` | Runtime → MessageHub | `{project_id, records}` | `{acked_sequences: [...]}` |
| `messageHub.syncInbox` | Runtime → MessageHub | `{project_id, last_sequence, limit}` | `{records: [...]}` |

### 7.2 Notification（单向推送）

| 方法 | 方向 | 说明 |
|---|---|---|
| `notify.externalEvent` | MessageHub → Runtime | 实时推送新到达的外部事件，payload 包含 `sequence`, `event_type`, `payload`, `source`, `scope`, `target` |

### 7.3 通信时序示例

**正常在线场景（Push 模式）**：

```
RabbitMQ ──► MessageHub ──► inbox 表 ──► notify.externalEvent ──► Runtime InboxHandler
                                                              │
                                                              ▼
                                                    EventRouter.publish(..., persist=False)
```

**Runtime 离线后重连（Sync 兜底）**：

```
Runtime reconnect
        │
        ▼
syncInbox(last_sequence=123)
        │
        ▼
MessageHub 查询 inbox.sequence > 123
        │
        ▼
返回积压消息 ──► Runtime 注入 EventBus
        │
        ▼
后续恢复接收 notify.externalEvent
```

---

## 8. 错误处理与边界情况

### 8.1 Runtime 崩溃 / 重启

1. RabbitMQ Consumer 不受影响，继续消费并写入 `inbox`。
2. Runtime 重启后，先执行 `syncInbox(last_sequence)` 补齐离线期间消息。
3. `OutboxProcessor` 扫描 `outbox` 未发送记录，继续推送。

### 8.2 WebSocket 断连

- **Outbox**：`publishBatch` 失败时不删除记录，退避重试。
- **Inbox**：`notify.externalEvent` 推送失败时消息留在 `inbox`，靠 `syncInbox` 恢复。

### 8.3 RabbitMQ 不可用

- **Inbound**：Consumer 自动重连，消息积压在 RabbitMQ 队列。
- **Outbound**：`publishBatch` 中失败的记录不返回 ack，`OutboxProcessor` 周期性重试。

### 8.4 消息循环防护

`InboxHandler` 调用 `EventRouter.publish(..., persist=False)`，确保外部事件注入内部后**不会再次写入 outbox**。

### 8.5 预留错误码

| 错误码 | 含义 |
|---|---|
| `-32101` | `messageHub.publishBatch` adapter 发送失败 |
| `-32102` | `messageHub.syncInbox` project 未注册到 MessageHub |
| `-32103` | inbox 消息格式非法 |
| `-32104` | outbox 消息超过最大重试次数 |

---

## 9. 测试策略

### 9.1 单元测试

- `MessageStore`：序列号单调性、幂等、事务边界。
- `EventRouter`：`external: true` 事件写 outbox，普通事件不写。
- `OutboxProcessor`：批量推送、失败重试、ack 删除。
- `RabbitMQAdapter`：publish/consume 基础行为。

### 9.2 集成测试

- **崩溃恢复**：Runtime 退出期间 RabbitMQ 消息被 inbox 缓存，重启后 `syncInbox` 可恢复。
- **断连恢复**：WebSocket 断开后 inbox 积压，重连后补齐。
- **端到端**：Instance behavior 发布 `external: true` 事件，经 outbox → MessageHub → RabbitMQ，再从 RabbitMQ 消费另一条消息，经 inbox → EventBus → Instance behavior。

---

## 10. 新增文件清单

| 文件 | 职责 |
|---|---|
| `src/runtime/event_router.py` | `EventRouter`：统一 publish 入口，代理 EventBus + 写日志 + 写 outbox |
| `src/runtime/outbox_processor.py` | `OutboxProcessor`：扫描 outbox 并批量推送到 MessageHub |
| `src/runtime/inbox_handler.py` | `InboxHandler`：处理 MessageHub 推送的外部事件 |
| `src/runtime/stores/message_store.py` | `MessageStore`：操作 `messagebox.db`（inbox/outbox/sequence） |
| `src/runtime/adapters/base.py` | `MessageAdapter` 抽象基类 |
| `src/runtime/adapters/rabbitmq_adapter.py` | `RabbitMQAdapter`：RabbitMQ 收发的第一个实现 |
| `src/runtime/server/message_hub.py` | `MessageHub`：Supervisor 内置的消息网关核心 |
| `tests/runtime/test_event_router.py` | EventRouter 单元测试 |
| `tests/runtime/test_outbox_processor.py` | OutboxProcessor 单元测试 |
| `tests/runtime/stores/test_message_store.py` | MessageStore 单元测试 |
| `tests/runtime/adapters/test_rabbitmq_adapter.py` | RabbitMQAdapter 单元测试 |
| `tests/runtime/server/test_message_hub.py` | MessageHub 单元测试 |

---

## 11. 设计决策记录

### 决策 1：MessageHub 内置在 Supervisor 中
- **原因**：部署最简单，与现有 WebSocket JSON-RPC 架构天然契合。未来若负载成为瓶颈，可平滑拆分为独立进程。

### 决策 2：`messagebox.db` 与 `runtime.db` 独立
- **原因**：`.lock` 文件锁保证同一时间只有一个 Runtime 能打开 `runtime.db`。若 inbox/outbox 放在 `runtime.db` 中，Supervisor 的 MessageHub 将无法写入崩溃 Project 的消息。

### 决策 3：Push 为主，Sync 兜底
- **原因**：在线时延迟最低；断连/崩溃时通过 inbox 缓存和 sequence 同步保证可靠性。

### 决策 4：Model 定义外发能力，`project.yaml` 定义外发目标
- **原因**：模型是"这个事件能不能外发"的元数据声明，不受部署环境变化影响；`project.yaml` 是"发到哪个 RabbitMQ"的运维配置，随环境变化。

### 决策 5：Runtime 不感知 MessageHub
- **原因**：业务代码保持纯净，`publish` 语义不变。外发是基础设施层的自动行为，通过 `EventRouter` 和 `OutboxProcessor` 透明完成。
