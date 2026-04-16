# MessageHub 外部消息统一网关设计文档

> 版本：v2.0  
> 日期：2026-04-16

---

## 1. 背景与目标

当前 `agent-studio` 的 `EventBus` 负责 instance 之间的内部事件分发，但外部事件（来自 RabbitMQ、MQTT 等）的接入以及 instance 产生的事件向外部系统的发送缺乏统一的抽象层。

本设计目标：

1. 为每个 Worker 进程建立统一的 **MessageHub**，负责所有"跨边界"消息的可靠收发与本地持久化。
2. Worker 不感知 MessageHub 的底层细节：业务代码只调用 `message_hub.publish()`，与内部事件完全一致的语义。
3. 通过可插拔的 **Channel** 适配不同的部署环境（直连 RabbitMQ、Supervisor 中继等）。
4. 第一批实现支持 **RabbitMQ Channel** 和 **Supervisor Channel**（JSON-RPC over WebSocket），其他协议通过 Channel 接口预留扩展。

---

## 2. 核心设计原则

- **Worker 独立拥有 MessageHub**：每个 `agent-studio run` 进程自带 `MessageHub`、本地 `messagebox.db`、InboxProcessor 和 OutboxProcessor。Worker 崩溃/重启不影响其他 Worker。
- **Channel 可插拔**：Worker 通过配置决定消息走哪个 Channel。可以是直连 RabbitMQ，也可以是通过 Supervisor 中转。
- **Supervisor 只做中继（SupervisorChannel 模式下）**：Supervisor 本身不持有 `messagebox.db`，只负责把 Worker 的 JSON-RPC 消息桥接到外部系统（如浏览器、RabbitMQ）。
- **统一入口**：`MessageHub` 是 Worker 内唯一的事件入口，封装了 `EventBus.publish()`、`EventLogStore.append()` 和 `MessageStore.outbox_enqueue()`。
- **消息先落盘，后处理/发送**：外部消息进入后先写 `inbox`；需要外发的消息先写 `outbox`。Channel 断连时消息安全积压在本地 DB，恢复后自动续传。

---

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Worker Process                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          MessageHub                                 │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                      EventBus (内部)                         │   │   │
│  │  │              纯内部订阅分发，供 InstanceManager 使用          │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                                                                     │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    │   │
│  │  │  messagebox.db  │◄──►│ InboxProcessor  │    │ OutboxProc  │◄──┤   │
│  │  │  - inbox        │    │  读取 inbox     │    │ 读取 outbox │   │   │
│  │  │  - outbox       │    │  注入 EventBus  │    │ 调用 Channel│   │   │
│  │  │  - sequences    │    │                 │    │             │   │   │
│  │  └─────────────────┘    └─────────────────┘    └──────┬──────┘    │   │
│  │                                                        │          │   │
│  │  ┌─────────────────────────────────────────────────────▼─────┐    │   │
│  │  │                        Channel                              │    │   │
│  │  │  ┌─────────────────┐      ┌─────────────────────────┐    │    │   │
│  │  │  │ RabbitMQChannel │      │    SupervisorChannel    │    │    │   │
│  │  │  │ 直连 RabbitMQ   │      │  WebSocket JSON-RPC     │    │    │   │
│  │  │  └─────────────────┘      │  到 Supervisor          │    │    │   │
│  │  │                           └─────────────────────────┘    │    │   │
│  │  └──────────────────────────────────────────────────────────┘    │   │
│  │                                                                     │   │
│  │  publish() ──► EventBus + EventLog + outbox                         │   │
│  │  register() ──► 代理给 EventBus                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────┐                                                   │
│  │  InstanceManager    │  调用 message_hub.register() / publish()         │
│  └─────────────────────┘                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
           RabbitMQChannel    │   SupervisorChannel
               │              │          │
               ▼              │          ▼
        ┌────────────┐        │   ┌──────────────┐
        │  RabbitMQ  │        │   │  Supervisor  │───► 浏览器 / 外部 RabbitMQ
        └────────────┘        │   └──────────────┘
                              │
```

---

## 4. 数据结构与存储 Schema

### 4.1 `messagebox.db`（独立 SQLite，每个 Worker 一份）

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

-- acked_at 语义：对于需要手动 ack 的 Channel（如 RabbitMQChannel），表示已调用 Channel.ack() 回 ack 给外部 broker 的时间；
-- 对于自动 ack 的 Channel（如 SupervisorChannel），写入时即设置 acked_at = received_at。

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
    error_count INTEGER DEFAULT 0,
    retry_after TEXT,
    last_error TEXT
);

-- 序列号管理
CREATE TABLE sequences (
    name TEXT PRIMARY KEY,
    value INTEGER DEFAULT 0
);

-- 处理器状态：InboxProcessor / OutboxProcessor 的游标和配置
CREATE TABLE processor_state (
    processor TEXT PRIMARY KEY,
    last_sequence INTEGER NOT NULL DEFAULT 0
);

-- 查询优化索引
CREATE INDEX idx_inbox_sequence ON inbox(sequence);
CREATE INDEX idx_outbox_sequence ON outbox(sequence);
CREATE INDEX idx_outbox_published_at ON outbox(published_at, error_count);
```

> **路径与并发**：`messagebox.db` 默认位于 `<project_dir>/messagebox.db`，与 `runtime.db` 同目录但独立文件。它由本 Worker 内的 InboxProcessor 和 OutboxProcessor 读写，建议在 `MessageStore` 连接初始化时启用 SQLite WAL 模式并配置 busy-timeout：`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`

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

- `inbox` 和 `outbox` 使用独立的序列号空间。
- **`RabbitMQChannel`** 使用 `name = 'inbox_rabbitmq'` 生成自己的单调序列号，**不使用 RabbitMQ delivery tag**（delivery tag 会随重连重置，无法保证唯一性）。
- **`SupervisorChannel`** 的 `sequence` 由 Supervisor 在推送 `notify.externalEvent` 时生成并分配，Worker 直接透传使用，确保 Supervisor 侧缓存有序。
- 序列号在 **单个 Worker 的 `messagebox.db` 范围内** 单调递增，用于本地幂等和断点续传。

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

Project 部署层面配置 Channel 类型和目标：

```yaml
project_id: factory-01
config:
  message_hub:
    channel: rabbitmq
    rabbitmq:
      host: localhost
      port: 5672
      exchange: factory.events
      routing_key: "#{event_type}"
```

或 Supervisor 模式：

```yaml
project_id: factory-01
config:
  message_hub:
    channel: supervisor
    supervisor:
      ws_url: "ws://localhost:8001/workers"
```

- Runtime 启动时读取 `message_hub.channel`，初始化对应的 Channel 实例。
- `RabbitMQChannel` 直接连接 RabbitMQ；`SupervisorChannel` 通过现有 WebSocket JSON-RPC 与 Supervisor 通信。

---

## 6. 组件接口

### 6.1 `MessageHub`

`MessageHub` 是 Worker 内唯一的事件入口和出口：

```python
class MessageHub:
    def __init__(
        self,
        event_bus: EventBus,
        event_log_store: EventLogStore | None,
        message_store: MessageStore,
        channel: Channel,
        model_events: dict[str, dict],
    ):
        self._bus = event_bus
        self._log_store = event_log_store
        self._msg_store = message_store
        self._channel = channel
        self._model_events = model_events
        self._inbox_processor = InboxProcessor(self)
        self._outbox_processor = OutboxProcessor(self)

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
        # 3. 如果需要外发且 persist=True，写 outbox
        #    persist=False 时跳过 outbox，防止消息循环（InboxProcessor 注入外部事件时使用）
        if persist and self._is_external(event_type):
            self._msg_store.outbox_enqueue(...)

    def register(self, instance_id: str, scope: str, event_type: str, handler: callable):
        """代理给 EventBus，供 InstanceManager 注册 behavior handler。"""
        self._bus.register(instance_id, scope, event_type, handler)

    def unregister(self, instance_id: str):
        self._bus.unregister(instance_id)

    def start(self) -> None:
        """启动 Channel、InboxProcessor、OutboxProcessor。"""

    def stop(self) -> None:
        """优雅停止各处理器和 Channel。"""

    def is_ready(self) -> bool:
        """返回 Channel 是否已连接并可正常工作，供 Runtime 生命周期判断实例启动时机。"""

    def on_channel_message(
        self, event_type: str, payload: dict, source: str, sequence: int,
        scope: str = "project", target: str | None = None
    ) -> None:
        """Channel 收到外部消息后回调：先写 inbox，再可能被 InboxProcessor 消费。"""
        self._msg_store.inbox_enqueue(
            sequence=sequence,
            event_type=event_type,
            payload=payload,
            source=source,
            scope=scope,
            target=target,
        )
```

### 6.2 `InboxProcessor`

轻量守护线程，负责从 inbox 读取消息并注入内部 EventBus：

```python
class InboxProcessor:
    def __init__(self, message_hub: MessageHub):
        self._hub = message_hub
        self._last_sequence = 0

    def start(self) -> None: ...
    def stop(self) -> None: ...
```

处理流程：
1. 启动时从 `processor_state` 表读取 `InboxProcessor` 上次处理到的 `last_sequence`（不存在则从 0 开始）。
2. 每 1s（可配置）扫描 `inbox` 表，读取 `sequence > last_sequence` 的记录。
3. 按 sequence 顺序调用 `MessageHub.publish(..., persist=False)` 注入内部 EventBus。
4. 更新 `last_sequence` 并写回 `processor_state` 表，标记消息为已交付（可同步更新 `inbox.delivered_at`）。
5. 幂等：若 `sequence <= last_sequence`，直接跳过。

> **注意**：`publish(..., persist=False)` 确保外部消息注入内部后**不会再次写入 outbox**，防止消息循环。

### 6.3 `OutboxProcessor`

轻量守护线程，负责从 outbox 读取消息并通过 Channel 发送：

```python
class OutboxProcessor:
    def __init__(self, message_hub: MessageHub):
        self._hub = message_hub

    def start(self) -> None: ...
    def stop(self) -> None: ...
```

处理流程：
1. 每 1s（可配置）扫描 `outbox` 表，读取 `published_at IS NULL AND error_count < max_retries AND (retry_after IS NULL OR retry_after <= now)` 的记录。
2. 调用 `Channel.send(event_type, payload, source, scope, target, sequence)` 发送。
3. `SendResult.SUCCESS`：删除对应记录（或标记 `published_at`）。
4. `SendResult.RETRYABLE`：递增 `error_count`，更新 `retry_after` 为退避后的时间（如指数退避：2^error_count 秒，最大 30s），更新 `last_error`。
5. `SendResult.PERMANENT`：立即停止重试，标记 `error_count = max_retries` 并记录 `last_error`，保留在 outbox 中供运维排查（或后续移入死信队列）。
6. 超过 `max_retries`（默认 10 次）的记录不再自动重试。

### 6.4 `Channel` 抽象基类

```python
from enum import Enum

class SendResult(Enum):
    SUCCESS = "success"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"

class Channel(ABC):
    @abstractmethod
    def start(self, inbound_callback: Callable[[str, dict, str, int, str, str | None], None]) -> None:
        """
        启动 Channel。
        inbound_callback 签名：
        (event_type, payload, source, sequence, scope, target) -> None
        """
        ...

    @abstractmethod
    def send(
        self,
        event_type: str,
        payload: dict,
        source: str,
        scope: str,
        target: str | None,
        sequence: int,
    ) -> SendResult:
        """发送单条消息，返回发送结果。"""
        ...

    @abstractmethod
    def stop(self) -> None: ...
```

#### `RabbitMQChannel`

- `start()`：启动 RabbitMQ Consumer，收到消息后回调 `inbound_callback`，并使用 `sequences` 表（`name = 'inbox_rabbitmq'`）生成单调递增的 `sequence`。不使用 RabbitMQ delivery tag，因为 delivery tag 会在重连后重置。
- `send()`：调用 `basic_publish` 发送到 RabbitMQ exchange。
- 断连时自动重连，inbound 消息由 RabbitMQ 队列持久化；outbound 消息由本地 outbox 缓存。

#### `SupervisorChannel`

- `start()`：建立 WebSocket 连接，注册 `notify.externalEvent` 处理器。收到 Supervisor 推送后回调 `inbound_callback`。
- `send()`：通过 WebSocket JSON-RPC 发送 `messageHub.publishBatch` 或单条 `messageHub.publish` 请求，等待 ack。
- 断连时 WebSocket 自动重连，outbound 消息由本地 outbox 缓存。inbound 消息不依赖 Supervisor 内存缓存——Supervisor 只做无状态桥接，Worker 离线期间消息由 Supervisor 后端的 RabbitMQ（或其他持久化队列）保存，Worker 重连后继续消费。

---

## 7. Runtime ↔ Supervisor 通信协议（SupervisorChannel 模式下）

在现有 WebSocket JSON-RPC 2.0 通道上新增以下方法：

### 7.1 Request/Response

| 方法 | 方向 | 参数 | 返回值 |
|---|---|---|---|
| `messageHub.publish` | Worker → Supervisor | `{project_id, sequence, event_type, payload, source, scope, target}` | `{acked: true}` |
| `messageHub.publishBatch` | Worker → Supervisor | `{project_id, records}` | `{acked_sequences: [...]}` |

### 7.2 Notification（单向推送）

| 方法 | 方向 | 说明 |
|---|---|---|
| `notify.externalEvent` | Supervisor → Worker | 推送外部消息，payload 包含 `sequence`, `event_type`, `payload`, `source`, `scope`, `target`。这是 best-effort notification；Worker 收到后先写 inbox，若写入失败（如磁盘满、DB 锁），消息仍可由 Supervisor 后端的持久化队列重试。 |

### 7.3 通信时序示例

**SupervisorChannel 正常在线场景（Push 模式）**：

```
外部系统 ──► Supervisor ──► notify.externalEvent ──► Worker SupervisorChannel
                                                       │
                                                       ▼
                                             MessageHub.on_channel_message
                                                       │
                                                       ▼
                                               inbox 表（持久化）
                                                       │
                                                       ▼
                                             InboxProcessor ──► EventBus
```

**SupervisorChannel WebSocket 断连恢复**：

1. Worker 检测到 WebSocket 断开。
2. OutboxProcessor 继续扫描 outbox，`send()` 返回 `SendResult.RETRYABLE`，消息不删除。
3. WebSocket 重连成功后，OutboxProcessor 自动恢复发送。
4. Inbound 消息：Supervisor 不做内存缓存，Worker 离线期间消息由 Supervisor 后端的 RabbitMQ（或其他持久化队列）保存；Worker 重连后继续接收 `notify.externalEvent`。

---

## 8. 错误处理与边界情况

### 8.1 Worker 崩溃 / 重启

1. `messagebox.db` 完整保留在 Project 目录中。
2. Worker 重启后启动 `MessageHub`，`InboxProcessor` 从 `last_sequence` 继续消费 inbox 积压。
3. `OutboxProcessor` 从 outbox 中恢复未发送的消息，通过 Channel 继续发送。

### 8.2 Channel 断连（RabbitMQ 或 WebSocket）

- **Inbound**：Consumer 断开，消息由外部持久化队列（RabbitMQ）兜底。对于 `SupervisorChannel`，Supervisor 不做内存缓存，离线期间消息由 Supervisor 后端队列保存。Channel 恢复后继续消费。
- **Outbound**：`send()` 返回 `RETRYABLE` 时 outbox 记录不删除，`OutboxProcessor` 按 `retry_after` 退避重试。

### 8.3 消息循环防护

`InboxProcessor` 调用 `MessageHub.publish(..., persist=False)`，确保外部事件注入内部后**不会再次写入 outbox**。

### 8.4 预留错误码

| 错误码 | 含义 |
|---|---|
| `-32101` | `messageHub.publish` / `publishBatch` 发送失败 |
| `-32102` | `messageHub` 相关 RPC project 未注册 |
| `-32103` | inbox 消息格式非法 |
| `-32104` | outbox 消息超过最大重试次数 |

---

## 9. 测试策略

### 9.1 单元测试

- `MessageStore`：序列号单调性、幂等、事务边界。
- `MessageHub`：`external: true` 事件写 outbox，普通事件不写；`publish(..., persist=False)` 不写 outbox。
- `InboxProcessor`：顺序消费、幂等（跳过已处理 sequence）、断点续传。
- `OutboxProcessor`：批量发送、失败重试、ack 删除。
- `RabbitMQChannel`：publish/consume 基础行为。
- `SupervisorChannel`：WebSocket 断连重试、JSON-RPC 调用封装。

### 9.2 集成测试

- **Worker 崩溃恢复**：模拟进程退出，重启后验证 inbox/outbox 消息可恢复。
- **Channel 断连恢复**：断开 RabbitMQ / WebSocket，验证消息不丢失，恢复后自动续传。
- **端到端（RabbitMQChannel）**：Instance behavior 发布 `external: true` 事件，经 outbox → RabbitMQ → 另一条消息回 inbox → EventBus → Instance behavior。
- **端到端（SupervisorChannel）**：验证 Supervisor 中转路径完整。

---

## 10. 新增文件清单

| 文件 | 职责 |
|---|---|
| `src/runtime/message_hub.py` | `MessageHub`：Worker 内统一的事件入口和出口 |
| `src/runtime/inbox_processor.py` | `InboxProcessor`：从 inbox 读取并注入 EventBus |
| `src/runtime/outbox_processor.py` | `OutboxProcessor`：从 outbox 读取并通过 Channel 发送 |
| `src/runtime/stores/message_store.py` | `MessageStore`：操作 `messagebox.db` |
| `src/runtime/channels/base.py` | `Channel` 抽象基类 |
| `src/runtime/channels/rabbitmq_channel.py` | `RabbitMQChannel`：直连 RabbitMQ |
| `src/runtime/channels/supervisor_channel.py` | `SupervisorChannel`：通过 WebSocket JSON-RPC 与 Supervisor 通信 |
| `src/runtime/server/supervisor_gateway.py` | Supervisor 侧接收 Worker `messageHub.publish` / `publishBatch` 并处理 `notify.externalEvent` 推送 |
| `tests/runtime/test_message_hub.py` | MessageHub 单元测试 |
| `tests/runtime/test_inbox_processor.py` | InboxProcessor 单元测试 |
| `tests/runtime/test_outbox_processor.py` | OutboxProcessor 单元测试 |
| `tests/runtime/stores/test_message_store.py` | MessageStore 单元测试 |
| `tests/runtime/channels/test_rabbitmq_channel.py` | RabbitMQChannel 单元测试 |
| `tests/runtime/channels/test_supervisor_channel.py` | SupervisorChannel 单元测试 |
| `tests/runtime/server/test_supervisor_gateway.py` | Supervisor 网关单元测试 |

---

## 11. 设计决策记录

### 决策 1：MessageHub 下沉到每个 Worker
- **原因**：保证 Worker 的独立性和故障隔离。一个 Worker 崩溃不会影响其他 Worker 的消息收发。每个 Worker 自己持有 `messagebox.db`，重启后可自给自足恢复。

### 决策 2：MessageHub 与 EventRouter 合并
- **原因**：Worker 内只需要一个统一的事件入口。业务代码和 `InstanceManager` 都面对同一个 `MessageHub` 对象，语义一致，减少概念负担。

### 决策 3：Channel 可插拔
- **原因**：不同部署环境需要不同的通信方式。边缘部署可以直接连 RabbitMQ；本地开发可以通过 Supervisor 中转。Channel 接口让两者共享同一套 MessageHub 逻辑。

### 决策 4：`messagebox.db` 与 `runtime.db` 独立
- **原因**：即使 `.lock` 文件锁保护 `runtime.db`，`messagebox.db` 仍然可以被 Worker 自由读写，不受 Supervisor 或其他进程影响。

### 决策 5：消息先落盘，后处理/发送
- **原因**：Channel 断连或 Worker 意外退出时，未处理/未发送的消息安全保存在 SQLite 中。恢复后自动续传，不需要依赖 RabbitMQ 的重试机制。

### 决策 6：Model 定义外发能力，`project.yaml` 定义 Channel 配置
- **原因**：模型是"这个事件能不能外发"的元数据声明；`project.yaml` 是"走哪个 Channel、发到哪"的运维配置，两者解耦。
