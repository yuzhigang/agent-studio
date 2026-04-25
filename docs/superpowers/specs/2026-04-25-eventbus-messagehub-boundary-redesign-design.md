# EventBus 与 MessageHub 边界重构设计文档

> 版本：v1.0
> 日期：2026-04-25

## 1. 背景

当前实现里，`EventBus`、`MessageHub`、`InboxProcessor`、`OutboxProcessor` 的职责边界不清晰，主要问题包括：

- `MessageHub` 同时承担通道管理、world 注册、外部消息缓冲、出站拦截、订阅解释等多重职责。
- `EventBus` 通过 `pre_publish_hook` 被 `MessageHub` 借用，内部领域事件与外部消息语义耦合。
- worker 级 `MessageHub` 的生命周期却被 world 停止流程反向控制，导致停一个 world 可能影响全部 world 的消息平面。
- 现有入站模型只有单条 `inbox` 记录和单个 `processed_at`，无法正确表达广播和部分失败。
- worker 级消息路由目前依赖 `event_type` 和 `model_events`，缺少显式 `world_id` 路由键，语义不稳定。

本设计目标是彻底拆清内部事件总线与外部消息平面，让两者通过显式边界连接，而不是通过 hook 隐式耦合。

## 2. 目标

### 2.1 目标

- 让 `EventBus` 只负责 world 内部事件分发，不再承载外部消息语义。
- 让 `MessageHub` 只负责 worker 级消息装配、生命周期和可靠缓冲。
- 让入站路由逻辑集中在 `InboxProcessor`，出站发送逻辑集中在 `OutboxProcessor`。
- 引入统一的 `MessageEnvelope`，强制 `world_id` 显式存在。
- 支持 `world_id="*"` 的显式广播，同时保持定向 world 投递。
- 让广播、部分失败、world 暂离线、worker 重启后的恢复都可被数据库状态正确表达。
- 让 world 对外收发消息走显式接口：`WorldMessageReceiver` / `WorldMessageSender`。

### 2.2 非目标

- 本次不引入新的 worker 内 broker 或独立消息中间件。
- 本次不改变 world 内部 `EventBus` 的基础发布/订阅语义。
- 本次不定义复杂的多租户鉴权协议，只定义消息边界与投递语义。

## 3. 核心原则

- 内外分离：内部事件不自动升级为外部消息。
- 显式优先：world 级消息路由必须依赖显式 `world_id`。
- 协调与执行分离：`MessageHub` 负责装配，Processor 负责执行。
- 消息本体与投递状态分离：一条消息可以对应多个 delivery。
- world 生命周期与 worker 消息平面生命周期分离。

## 4. 总体架构

### 4.1 重构后的角色

- `EventBus`
  - 单个 world 内部组件。
  - 负责 instance / scene / trigger 间的内部事件分发。
  - 不再被 `MessageHub` 监听。

- `MessageHub`
  - 单个 worker 内部组件。
  - 负责装配 `Channel`、`MessageStore`、`InboxProcessor`、`OutboxProcessor`。
  - 维护 `world_id -> WorldMessageReceiver` 注册表。
  - 不负责具体路由执行，不直接调用 `EventBus.publish()`。

- `InboxProcessor`
  - 负责入站消息展开、逐 world 投递、重试、死信。
  - 是真正的入站路由执行器。

- `OutboxProcessor`
  - 负责出站消息发送、ack、重试、失败终结。

- `WorldMessageReceiver`
  - world 的入站边界接口。
  - 将 `MessageEnvelope` 转译为 world 内部输入。

- `WorldMessageSender`
  - world 的出站边界接口。
  - world 通过它显式构造并提交外部消息。

### 4.2 数据流

入站链路：

`Channel -> MessageHub.on_inbound(envelope) -> MessageStore.inbox_append(envelope) -> InboxProcessor -> WorldMessageReceiver.receive(envelope) -> world runtime / EventBus`

出站链路：

`world runtime -> WorldMessageSender.send(...) -> MessageHub.enqueue_outbound(envelope) -> MessageStore.outbox_append(envelope) -> OutboxProcessor -> Channel.send(envelope)`

## 5. 消息契约

统一信封类型命名为 `MessageEnvelope`。

```python
@dataclass
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

字段语义：

- `message_id`
  - 全局唯一消息 ID。
  - 用于去重、追踪、重试。

- `world_id`
  - 必填。
  - 精确值表示定向投递到某个 world。
  - `"*"` 表示显式广播到当前 worker 上所有已注册 world。

- `event_type`
  - 消息类型。

- `payload`
  - 业务负载。

- `source`
  - 字符串发送方标识。

- `scope`
  - 消息进入 world 后的内部分发作用域，默认 `"world"`。

- `target`
  - world 内部目标标识，字符串。
  - 仅在进入 world 后参与内部投递。

- `trace_id`
  - 链路跟踪 ID。

- `headers`
  - channel 或集成层扩展元数据。

## 6. 路由模型

### 6.1 worker 级路由

- `world_id="factory-a"`：只投递给 `factory-a` 对应的 `WorldMessageReceiver`。
- `world_id="*"`：显式广播给当前 worker 上所有已注册 world 的 `WorldMessageReceiver`。

禁止以下行为：

- 缺省 `world_id`。
- 依赖 `event_type` 或 `model_events` 推断目标 world。
- 使用同名事件自动扩散到多个 world。

### 6.2 world 内路由

`target` 和 `scope` 只在消息进入某个 world 后生效：

- `world_id` 决定“进哪个 world”。
- `scope` / `target` 决定“进了 world 以后给谁”。

两层语义必须分离，不能混为一层 worker 级路由。

## 7. 组件职责

### 7.1 MessageHub

职责：

- 管理 `Channel` 生命周期。
- 管理 `InboxProcessor` / `OutboxProcessor` 生命周期。
- 管理 `world_id -> WorldMessageReceiver` 注册表。
- 接收入站信封并写入 `inbox`。
- 接收出站信封并写入 `outbox`。

接口建议：

```python
class MessageHub:
    def register_world(self, world_id: str, receiver: WorldMessageReceiver) -> None: ...
    def unregister_world(self, world_id: str) -> None: ...
    def enqueue_outbound(self, envelope: MessageEnvelope) -> None: ...
    def on_inbound(self, envelope: MessageEnvelope) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def is_ready(self) -> bool: ...
```

不再承担：

- 解释 `model_events`
- 监听 `EventBus`
- 通过 hook 拦截内部事件
- 直接执行业务分发

### 7.2 InboxProcessor

职责：

- 拉取 `inbox` 中待展开或待投递消息。
- 按 `world_id` 展开 delivery 目标。
- 调用 `WorldMessageReceiver.receive(envelope)`。
- 记录 delivery 成功、失败、重试、死信。
- 根据 delivery 聚合更新 `inbox` 总体状态。

### 7.3 OutboxProcessor

职责：

- 拉取 `outbox` 中待发送消息。
- 调用 `Channel.send(envelope)`。
- 记录 sent / retry / dead。

### 7.4 WorldMessageReceiver

职责：

- 作为 world 入站边界。
- 将 `MessageEnvelope` 转译成 world 内部输入。
- 用明确成功 / 可重试失败 / 永久失败的结果反馈给 `InboxProcessor`。

建议接口：

```python
class WorldMessageReceiver(Protocol):
    async def receive(self, envelope: MessageEnvelope) -> None: ...
```

### 7.5 EventBusMessageAdapter

- `WorldMessageReceiver` 的默认实现。
- 负责把 `MessageEnvelope` 适配到 world 内部 `EventBus`。
- 该类是边界适配器，不参与消息存储和状态管理。

示意：

```python
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

### 7.6 WorldMessageSender

职责：

- 作为 world 出站边界。
- 从 world 内部构造 `MessageEnvelope`。
- 强制填充 `world_id`、`source`、`trace_id` 等字段。
- 调用 `MessageHub.enqueue_outbound(envelope)`。

建议接口：

```python
class WorldMessageSender:
    def __init__(self, world_id: str, hub: MessageHub, source: str): ...

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
    ) -> str: ...
```

## 8. 存储模型

### 8.1 inbox

存消息本体，不存逐 world 投递状态。

```sql
CREATE TABLE inbox (
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
```

`status` 取值：

- `pending`
- `expanded`
- `completed`
- `failed`

### 8.2 inbox_deliveries

存每条消息对每个目标 world 的投递状态。

```sql
CREATE TABLE inbox_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    target_world_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_count INTEGER NOT NULL DEFAULT 0,
    retry_after TEXT,
    last_error TEXT,
    delivered_at TEXT,
    UNIQUE(message_id, target_world_id),
    FOREIGN KEY(message_id) REFERENCES inbox(message_id)
);
```

`status` 取值：

- `pending`
- `delivered`
- `retry`
- `failed`
- `dead`

### 8.3 outbox

```sql
CREATE TABLE outbox (
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
```

`status` 取值：

- `pending`
- `retry`
- `sent`
- `dead`

### 8.4 设计约束

- `inbox` 只表达“消息是否进入 worker”。
- `inbox_deliveries` 表达“是否送达每个目标 world”。
- `outbox` 表达“是否成功发给外部通道”。
- 广播消息必须展开成多条 delivery。
- `inbox` 不能再使用单一 `processed_at` 表达整体完成状态。

## 9. 失败处理与幂等

### 9.1 入站

- `receive()` 成功返回：delivery -> `delivered`
- 抛出 `RetryableDeliveryError`：delivery -> `retry`
- 抛出 `PermanentDeliveryError`：delivery -> `failed` 或 `dead`

`inbox.status` 聚合规则：

- 所有 delivery 为 `delivered` -> `completed`
- 存在 `pending` / `retry` -> `expanded`
- 全部为终态且至少一个 `failed` / `dead` -> `failed`

### 9.2 出站

`Channel.send(envelope)` 返回三类结果：

- `SUCCESS`
- `RETRYABLE`
- `PERMANENT`

映射：

- `SUCCESS` -> `sent`
- `RETRYABLE` -> `retry`
- `PERMANENT` -> `dead`

### 9.3 world 上下线

- `register_world()` 只影响未来新展开的消息。
- `unregister_world()` 不删除既有 delivery。
- world 暂时不在线时，对应 delivery 应进入 `retry`，而非直接失败。
- 只有 world 被确认永久删除，才允许把相关 delivery 终结为 `failed` / `dead`。

### 9.4 幂等

- `inbox` 以 `message_id` 去重。
- `inbox_deliveries` 以 `(message_id, target_world_id)` 去重。
- `outbox` 以 `message_id` 去重。
- `MessageHub` 只保证 worker 级不重复处理同一信封，不替代 world 内业务幂等。

## 10. 代码结构建议

建议新增 `src/runtime/messaging/` 目录：

- `envelope.py`
- `hub.py`
- `inbox_processor.py`
- `outbox_processor.py`
- `store.py`
- `sqlite_store.py`
- `errors.py`
- `world_receiver.py`
- `world_sender.py`

现有类迁移建议：

- `src/runtime/event_bus.py`
  - 保留为 world 内部事件总线。
  - 去掉对 `MessageHub` 的隐式依赖预期。

- `src/runtime/message_hub.py`
  - 拆分，不再保留为大一统实现。
  - 删除 `_subscriptions`、`model_events`、hook 驱动出站逻辑。

- `src/runtime/inbox_processor.py`
  - 重写为基于 `world_id` + `inbox_deliveries` 的执行器。

- `src/runtime/outbox_processor.py`
  - 重写为基于 `MessageEnvelope` 的出站执行器。

## 11. Worker 与 World 的装配方式

### 11.1 WorldRegistry

`WorldRegistry.load_world()` 返回的 bundle 建议新增：

- `message_receiver`
- `message_sender`

原则：

- `WorldRegistry` 负责 world 内对象创建。
- `WorkerManager` / worker CLI 负责 worker 级对象装配。
- `WorldRegistry` 不直接创建 `MessageHub`。

### 11.2 worker 启动

worker 启动后：

1. 创建单个 `MessageHub`
2. 为每个已加载 world 注册 `message_receiver`
3. 将 `message_sender` 注入 world bundle
4. 启动 hub、processor、channel

world 停止时：

- 只 `unregister_world(world_id)`
- 不停止整个 shared `MessageHub`

worker 退出时：

- 统一停止 `MessageHub`

## 12. 迁移路径

### 12.1 步骤

1. 新增 `MessageEnvelope`、`WorldMessageReceiver`、`WorldMessageSender`、`EventBusMessageAdapter`
2. 重写 `MessageHub` 内部结构，但保留 worker 启动入口形式
3. 让 worker 改为注册 `world_id + message_receiver`
4. 用 `WorldMessageSender` 替换现有 hook 驱动外发路径
5. 删除旧的 `model_events`、worker 级 event_type 订阅和单表 inbox 模型

### 12.2 迁移原则

- 先建立新边界，再切换实现。
- 先入站，再出站。
- 先兼容，再删除。
- 每一步都必须能独立回归测试。

## 13. 测试策略

### 13.1 单元测试

- `MessageEnvelope` 序列化 / 反序列化
- `InboxProcessor` 的单 world / 广播 / world 缺失 / 部分失败
- `OutboxProcessor` 的 success / retry / dead
- `EventBusMessageAdapter` 的适配行为

### 13.2 存储测试

- `inbox`
- `inbox_deliveries`
- `outbox`
- 去重约束
- restart 后继续处理 pending / retry

### 13.3 集成测试

- 单 worker 多 world 定向投递
- `world_id="*"` 广播
- 广播时部分成功部分失败
- world 暂离线再恢复
- 停一个 world 不影响其他 world

### 13.4 强制回归项

- world 停止不会关闭 shared hub
- 相同 `message_id` 不会重复投递
- world 内普通 `EventBus.publish()` 不会自动进入 outbox
- 只有 `WorldMessageSender.send()` 才会产生外部出站消息

## 14. 完成标志

以下条件同时成立，才视为本次边界重构完成：

- `EventBus` 不再承载外部消息语义。
- `MessageHub` 不再窥探 world 内部模型与事件。
- 广播、部分失败、暂离线、重启恢复都能通过 `messagebox.db` 状态清晰表达。
- world 的对外收发均通过 `WorldMessageReceiver` / `WorldMessageSender` 显式完成。
