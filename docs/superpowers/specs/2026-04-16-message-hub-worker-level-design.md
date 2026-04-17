# MessageHub Worker 级控制平面设计文档

> 版本：v1.0  
> 日期：2026-04-16

---

## 1. 背景与目标

当前 `agent-studio` 的 `EventBus` 负责 instance 之间的内部事件分发，但外部事件（来自 RabbitMQ、MQTT 等）的接入以及 instance 产生的事件向外部系统的发送缺乏统一的抽象层。

本设计目标：

1. 为每个 **Worker 进程**建立统一的 **MessageHub**，作为所有 Project 的"事件控制平面"。
2. MessageHub 与 Project 完全解耦：Project 代码不感知 MessageHub 的存在。
3. 通过可插拔的 **Channel** 适配不同的部署环境（直连 RabbitMQ、WebSocket JSON-RPC 等）。
4. 第一批实现支持 **RabbitMQ Channel** 和 **JSON-RPC Channel**（通用 WebSocket JSON-RPC），其他协议通过 Channel 接口预留扩展。

---

## 2. 核心设计原则

- **Worker 级 MessageHub**：一个 Worker 进程内只存在一个 MessageHub 实例，所有加载的 Project 共享它。无论是 `agent-studio run`（单 project）还是 `agent-studio run-inline`（多 project），MessageHub 都是单例。
- **Project 零感知**：MessageHub 通过 `EventBus.pre_publish_hook` 拦截事件，不修改 project 代码、不污染 EventBus 的公共接口语义。
- **独立存储**：MessageHub 拥有独立的 `messagebox.db`，与 project 的 `runtime.db` 解耦。`inbox` / `outbox` 表不再包含 `project_id`。
- **订阅表路由**：Project 加载时向 MessageHub 注册其订阅的事件列表。外部消息进入 inbox 后，InboxProcessor 查订阅表决定广播给哪些 project 的 EventBus。
- **Channel 可插拔**：Worker 通过配置决定消息走哪个 Channel。可以是直连 RabbitMQ，也可以是通过 WebSocket JSON-RPC 通道（如 Supervisor、自定义网关等）中转。
- **JsonRpcChannel 无状态桥接**：`JsonRpcChannel` 是一个通用的 WebSocket JSON-RPC Channel，可指向任何 JSON-RPC over WebSocket 服务端（包括 Supervisor，但不限于 Supervisor）。它本身不持有 MessageHub 数据，只做无状态的消息收发。
- **异步优先（Asyncio-First）**：所有跨边界 I/O（Channel 连接、Processor 轮询、MessageHub 生命周期）均基于 `asyncio`。

---

## 3. 架构总览

```
┌────────────────────────────────────────────────────────────────┐
│                        Worker Process                          │
│                                                                │
│   ┌──────────────────────────────────────────────────────┐    │
│   │                    MessageHub                        │    │
│   │  ┌──────────────────────────────────────────────┐   │    │
│   │  │           messagebox.db                       │   │    │
│   │  │  ┌─────────┐        ┌─────────┐              │   │    │
│   │  │  │  inbox  │◄──────►│ Inbox   │──────────────┤   │    │
│   │  │  │         │        │Processor│              │   │    │
│   │  │  └─────────┘        └────┬────┘              │   │    │
│   │  │  ┌─────────┐        ┌────┴────┐              │   │    │
│   │  │  │ outbox  │◄──────►│ Outbox  │              │   │    │
│   │  │  │         │        │Processor│              │   │    │
│   │  │  └─────────┘        └────┬────┘              │   │    │
│   │  └──────────────────────────┼───────────────────┘   │    │
│   │                             │                        │    │
│   │   publish intercepted       │   Channel send/recv    │    │
│   │        ▲                    │         ▲              │    │
│   │        │                    │         │              │    │
│   │   ┌────┴────────────────────┴─────────┐             │    │
│   │   │         Subscription Table         │             │    │
│   │   │   event_type → [project_id, ...]   │             │    │
│   │   └────────────────────────────────────┘             │    │
│   └──────────────────────────────────────────────────────┘    │
│         ▲                                  │                  │
│         │ pre_publish hook                 │ Channel          │
│   ┌─────┴──────┐    ┌─────────────┐       │ (RabbitMQ/WS)    │
│   │ Project A  │    │  Project B  │       │                  │
│   │  EventBus  │    │  EventBus   │       │                  │
│   └────────────┘    └─────────────┘       ▼                  │
│                                               External Broker  │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. EventBus Hook 与订阅机制

### 4.1 EventBus 的 `pre_publish_hook`

在 `EventBus` 内部增加一个轻量 hook 列表，不破坏原有接口：

```python
class EventBus:
    def __init__(self):
        self._handlers = {}
        self._pre_publish_hooks: list[Callable] = []

    def add_pre_publish_hook(
        self,
        hook: Callable[[str, dict, str, str, str | None], None]
    ) -> None:
        self._pre_publish_hooks.append(hook)

    def remove_pre_publish_hook(self, hook) -> None:
        self._pre_publish_hooks.remove(hook)

    def publish(self, event_type, payload, source, scope, target=None):
        for hook in self._pre_publish_hooks:
            hook(event_type, payload, source, scope, target)
        for handler in self._handlers.get((scope, event_type), []):
            handler(event_type, payload, source)
```

**约束**：hook 是同步调用、无副作用阻塞。MessageHub 的 hook 内部只做两件事：
1. 如果是 external 事件，写 `messagebox.db` 的 outbox。
2. 立刻返回，不干预 EventBus 的正常分发。

### 4.2 Project 注册到 MessageHub

Worker 加载 project 时执行注册：

```python
message_hub.register_project(
    project_id="factory-01",
    event_bus=bus,
    model_events={"order.created": {"external": True}},
)
```

MessageHub 内部做两件事：
1. **订阅表更新**：`"order.created" -> {"factory-01", ...}`。
2. **挂载 hook**：给该 project 的 `event_bus` 添加 `pre_publish_hook`。

卸载 project 时：

```python
message_hub.unregister_project("factory-01")
```

做反向清理：移除 hook、从订阅表删除该 project。

### 4.3 订阅表维护

订阅表是内存字典：

```python
self._subscriptions: dict[str, set[str]] = {}  # event_type -> {project_id, ...}
self._projects: dict[str, tuple[EventBus, Callable]] = {}  # project_id -> (event_bus, hook_ref)
```

**订阅来源**：从 `model_events` 读取。MVP 阶段约定 `external: true` 的事件默认表示"既外发又接收"。

### 4.4 路由规则

**Outbound（内部 → 外部）**：
- `pre_publish_hook` 捕获到事件。
- 检查 `model_events`，若 `external=True`，写 outbox。
- 不检查订阅表——source project 产生的事件天然有资格外发。

**Inbound（外部 → 内部）**：
- Channel 收到消息后写入 inbox。
- InboxProcessor 查订阅表 `"order.created" -> {"factory-01", "factory-02"}`。
- 向所有订阅 project 的 EventBus 广播 `publish()`。
- 各 EventBus 再按自己的 `scope` / `target` 过滤分发。

---

## 5. messagebox.db Schema 与存储设计

### 5.1 数据库位置与生命周期

- **路径**：`~/.agent-studio/workers/{worker_id}/messagebox.db`
  - `worker_id` 可用进程 PID 或启动时生成的 UUID。
- **模式**：启用 WAL（`PRAGMA journal_mode=WAL`）。
- **清理**：MVP 阶段暂不做自动清理。

### 5.2 Schema

```sql
CREATE TABLE inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    target TEXT,
    received_at TEXT NOT NULL,
    processed_at TEXT
);
CREATE INDEX idx_inbox_processed_at ON inbox(processed_at);

CREATE TABLE outbox (
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
CREATE INDEX idx_outbox_published_at ON outbox(published_at, error_count, retry_after);
```

### 5.3 关键变化：去掉了 `project_id`

MessageHub 是 worker 级的，inbox / outbox 不再包含 `project_id`。路由由 InboxProcessor 根据订阅表完成。

### 5.4 MessageStore 接口调整

```python
class MessageStore(ABC):
    @abstractmethod
    def inbox_enqueue(self, event_type: str, payload: dict, source: str, scope: str, target: str | None) -> int: ...
    @abstractmethod
    def inbox_mark_processed(self, message_id: int) -> None: ...
    @abstractmethod
    def inbox_read_pending(self, limit: int) -> list[dict]: ...

    @abstractmethod
    def outbox_enqueue(self, event_type: str, payload: dict, source: str, scope: str, target: str | None) -> int: ...
    @abstractmethod
    def outbox_mark_sent(self, message_id: int) -> None: ...
    @abstractmethod
    def outbox_read_pending(self, limit: int) -> list[dict]: ...
    @abstractmethod
    def outbox_update_error(self, message_id: int, error_count: int, retry_after: str | None, last_error: str | None) -> None: ...
```

### 5.5 与 project runtime.db 的边界

| 数据 | 存储位置 | 原因 |
|---|---|---|
| `inbox` / `outbox` | `messagebox.db` (worker 级) | 控制平面的持久化缓冲 |
| `event_log` | `runtime.db` (project 级) | 业务状态的事件溯源回放 |
| `instances` snapshot | `runtime.db` (project 级) | checkpoint 恢复 |

**设计保证**：`pre_publish_hook` 只写 outbox，不再写任何 project 的 `event_log`。`event_log` 保持纯业务语义。

---

## 6. InboxProcessor / OutboxProcessor 与 Channel

### 6.1 InboxProcessor

`asyncio.Task` 轮询 inbox：

1. 读取 `processed_at IS NULL`，按 `id` 升序。
2. 查订阅表得到目标 project 集合。
3. 对每个 project 调用其 `EventBus.publish()`。
4. **全部分发成功后**，`inbox_mark_processed(msg_id)`。

**边界**：
- 某个 project 分发失败不影响其他 project。
- 至少一个失败则该 inbox 记录不标记 processed，下次重试。
- 订阅表为空时直接标记 processed，避免死消息。

### 6.2 OutboxProcessor

`asyncio.Task` 轮询 outbox：

1. 读取 `published_at IS NULL AND error_count < max_retries AND (retry_after IS NULL OR retry_after <= now)`。
2. 调用 `await channel.send(...)`。
3. `SUCCESS` → `outbox_mark_sent`；`RETRYABLE` → 指数退避；`PERMANENT` → 标记 `error_count = max_retries`。

### 6.3 Channel 接口

保持纯异步：

```python
class Channel(ABC):
    async def start(self, inbound_callback) -> None: ...
    async def send(self, event_type, payload, source, scope, target) -> SendResult: ...
    async def stop(self) -> None: ...
    def is_ready(self) -> bool: ...
```

Channel 的 `inbound_callback` 指向 `MessageHub.on_channel_message`，直接进入 inbox。

### 6.4 与当前实现的关键差异

| 点 | 当前实现（per-project） | 新设计（per-worker） |
|---|---|---|
| Inbox 路由 | 发给单一 project | 查订阅表广播给多个 project |
| outbox 来源 | 单一 project | 所有 project |
| Channel 数量 | N project × 1 | 1 Worker × 1（MVP） |
| `send()` 调用方 | per-project OutboxProcessor | worker 级 OutboxProcessor |

---

## 7. Worker 启动流程与生命周期

### 7.1 `run` 模式（单 project）

```python
def run_project(project_dir, supervisor_ws=None, ...):
    registry = ProjectRegistry(...)
    bundle = registry.load_project(project_id)

    message_hub = _get_or_create_message_hub(bundle)
    bus = bundle["event_bus_registry"].get_or_create(project_id)
    message_hub.register_project(project_id, bus, bundle.get("model_events", {}))
    await message_hub.start()
```

### 7.2 `run-inline` 模式（多 project）

```python
def run_inline(project_dirs):
    message_hub = _get_or_create_message_hub(...)
    for project_dir in project_dirs:
        bundle = registry.load_project(project_id)
        bus = bundle["event_bus_registry"].get_or_create(project_id)
        message_hub.register_project(project_id, bus, bundle.get("model_events", {}))
    await message_hub.start()
```

### 7.3 MessageHub 单例机制

```python
_worker_message_hub: MessageHub | None = None

def _get_or_create_message_hub(bundle: dict | None = None) -> MessageHub:
    global _worker_message_hub
    if _worker_message_hub is None:
        channel = _build_channel(bundle) if bundle else None
        _worker_message_hub = MessageHub(
            msg_store=SQLiteMessageStore(worker_id=...),
            channel=channel,
        )
    return _worker_message_hub
```

### 7.4 优雅停机

```python
def _shutdown(signum, frame):
    message_hub = _get_worker_message_hub()
    if message_hub:
        asyncio.run(message_hub.stop())
        for project_id in list(message_hub.registered_projects()):
            message_hub.unregister_project(project_id)
```

**顺序**：先 stop MessageHub（停止 Processor 和 Channel），再 unregister project（移除 hook），最后 unload project。

### 7.5 动态 project 加载/卸载

支持运行时热加载：
- 加载：`message_hub.register_project(...)`
- 卸载：`message_hub.unregister_project(project_id)`

MessageHub 本身无需重启。

---

## 8. 测试策略

### 8.1 单元测试

- `SQLiteMessageStore`：inbox/outbox 读写、无 `project_id` 的新 schema。
- `MessageHub`：
  - `register_project` / `unregister_project` 正确挂载/移除 hook。
  - `pre_publish_hook` 只把 `external=True` 事件写入 outbox。
  - 订阅表路由：单播、广播、空订阅。
- `InboxProcessor`：轮询、分发到多个 project EventBus、失败重试、空订阅直接标记 processed。
- `OutboxProcessor`：发送、重试、错误标记。
- `JsonRpcChannel` / `RabbitMQChannel`：保持不变，复用现有测试。

### 8.2 集成测试

- `run-inline` 双 project 场景：
  - Project A 产生 `external=True` 事件 → outbox 有记录。
  - 模拟外部消息回环 → InboxProcessor 同时分发给 Project A 和 Project B。
- Worker 重启恢复：messagebox.db 数据不丢，新 Worker 进程继续消费/发送。

---

## 9. 设计决策记录

### 决策 1：MessageHub 提升到 Worker 级
- **原因**：`run-inline` 等多 project 场景下，per-project MessageHub 会导致资源冗余和无法统一策略。Worker 级单例更符合"控制平面"的定位。

### 决策 2：独立的 messagebox.db
- **原因**：把控制平面数据与业务数据（runtime.db 中的 event_log、instances）物理隔离，便于独立维护、迁移和故障排查。

### 决策 3：EventBus pre_publish_hook
- **原因**：在不修改 project 代码的前提下实现全局拦截，是最轻量、最彻底的解耦方式。

### 决策 4：订阅表维护在内存中
- **原因**：订阅信息来源于 project 加载时的静态 model 配置，变化频率极低。内存字典足够高效，无需落盘到 messagebox.db。

### 决策 5：Inbox 采用广播语义
- **原因**：一个外部事件（如 `order.created`）可能多个 project 都关心。广播是最自然的路由方式，各 project EventBus 再用自己的 `scope` / `target` 做二次过滤。
