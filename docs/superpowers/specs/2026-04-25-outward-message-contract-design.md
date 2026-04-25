# Outward Message Contract 设计文档

> 版本：v1.0
> 日期：2026-04-25

## 1. 背景

当前 `EventBus / MessageHub` 边界重构已经基本完成，但 `triggerEvent external=true` 的消息契约仍然保留了上一版设计的残余语义，主要问题包括：

- `MessageEnvelope.world_id` 同时承担过来源 world 和目标 world 两种含义，出站与入站解释不统一。
- `triggerEvent external=true` 仍然使用 `targetWorldId`，但这与当前“通过 MessageHub 对外发布”的语义不匹配。
- 顶层消息的 `target` 与 world 内部事件的实例目标语义混在一起，字段含义不稳定。
- `scope` 已经支持 `world` 和 `scene:<scene_id>` 两类内部传播范围，但这层语义尚未在外发契约上明确固定。

本设计目标是把 outbound / inbound 的顶层消息契约重新命名并收紧，让 `external=true` 明确表示“从当前 world 对外发布”，而不是“发送到某个目标 world”。

## 2. 目标

### 2.1 目标

- 用显式字段区分 world 间路由和 world 内部路由。
- 让 outbound 消息天然表达“来自哪个 world”，而不是“发给哪个 world”。
- 删除 `targetWorldId` 这类与当前语义不匹配的 action 字段。
- 保留 `scope` 和 `target` 作为 world 内事件传播语义。
- 让 inbound / outbound 对顶层 world 路由字段的解释完全一致。

### 2.2 非目标

- 本次不引入新的 broker、topic、exchange 抽象。
- 本次不改变 `EventBus` 的基础订阅/分发模型。
- 本次不定义跨系统鉴权或多租户协议。

## 3. 核心原则

- 顶层消息路由与 world 内部实例路由分层表达。
- `external=true` 表示“通过 MessageHub 对外发布”，不表示“指定目标 world”。
- world 内部传播仍然由 `scope + target` 决定。
- 路由字段强约束，业务负载允许表达式求值。

## 4. 总体思路

### 4.1 顶层消息字段

将当前 `MessageEnvelope` 中的 `world_id` 替换为：

- `source_world`
- `target_world`

保留 world 内部事件目标字段：

- `target`

这里的 `target` 明确表示 world 内部实例目标，不再承担跨 world 路由含义。

### 4.2 两层路由模型

- 顶层消息平面：
  - `source_world`
  - `target_world`

- world 内部事件平面：
  - `scope`
  - `target`

两层语义不能混用。

## 5. MessageEnvelope 契约

建议统一为：

```python
@dataclass
class MessageEnvelope:
    message_id: str
    source_world: str | None = None
    target_world: str | None = None
    event_type: str = ""
    payload: dict = field(default_factory=dict)
    source: str | None = None
    scope: str = "world"
    target: str | None = None
    trace_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
```

字段语义：

- `message_id`
  - 全局唯一消息 ID。

- `source_world`
  - 该消息从哪个 world 发出。
  - outbound 时由当前 world 自动填写。
  - inbound 时如果消息来自系统外部，可以为空，也可以由接入侧补齐。

- `target_world`
  - 该消息要进入哪个 world。
  - 定向投递时为具体 world id。
  - 广播时为 `"*"`。
  - 为空时表示不触发任何 world 路由处理。

- `event_type`
  - 事件类型。

- `payload`
  - 业务负载。

- `source`
  - 更细粒度的来源标识，例如 instance id、外部系统名。

- `scope`
  - world 内传播范围。
  - 允许值：
    - `world`
    - `scene:<scene_id>`

- `target`
  - world 内部实例目标。
  - 只在消息已经进入某个 world 后参与路由。

- `trace_id`
  - 链路追踪 ID。

- `headers`
  - 扩展元数据，类型固定为 `dict[str, str]`。

## 6. 路由语义

### 6.1 Outbound

当 behavior 中执行：

```yaml
- type: triggerEvent
  name: ladleLoaded
  external: true
```

语义为：

- 从当前 world 对外发布一条消息。
- 该消息进入 `MessageHub` 和 `outbox`。
- 默认不指定目标 world。

因此 outbound 默认字段为：

- `source_world = 当前 world_id`
- `target_world = null`
- `source = 当前 instance.id` 或调用上下文来源

其中 `target_world = null` 的含义是：

- 该消息只是被发布到外部消息平面；
- 默认不触发任何 worker 级 world 路由处理；
- 只有后续某个接入方重新写入了明确的 `target_world`，它才会再次进入某个 world。

### 6.2 Inbound

外部消息要进入某个 world 时，必须显式带 `target_world`：

- `target_world = "factory-a"`：定向投递到 `factory-a`
- `target_world = "*"`：广播给当前 worker 上所有已注册 world
- `target_world = null`：默认不进行任何处理，不进入 world，worker 不做猜测式投递

`InboxProcessor` 只基于 `target_world` 决定 worker 级路由。

### 6.3 World 内部投递

消息进入某个 world 后，再由 `scope + target` 决定内部投递：

- `scope = world` 且 `target = null`
  - world 内广播

- `scope = world` 且 `target = ladle-001`
  - world 范围内定向投给该实例

- `scope = scene:sceneId1` 且 `target = null`
  - 只在该 scene 范围内广播

- `scope = scene:sceneId1` 且 `target = ladle-001`
  - 只在该 scene 中定向投给该实例

## 7. triggerEvent external=true 契约

### 7.1 推荐写法

```yaml
- type: triggerEvent
  name: ladleLoaded
  external: true
  scope: scene:sceneId1
  target: ladle-001
  payload:
    ladleId: this.id
    steelAmount: this.variables.steelAmount
  traceId: trace-001
  headers:
    priority: high
```

### 7.2 字段约束

保留字段：

- `type`
- `name`
- `external`
- `payload`
- `scope`
- `target`
- `traceId`
- `headers`

删除字段：

- `targetWorldId`

### 7.3 校验规则

- `external=true` 时，`name` 必填。
- `payload` 必须是 object。
- `scope` 缺省时默认取当前 instance.scope。
- `scope` 必须满足：
  - `world`
  - 或 `scene:<scene_id>`
- `target` 必须是字符串或空。
- `traceId` 必须是字符串或空。
- `headers` 必须是 `dict[str, str]`。

### 7.4 表达式规则

- `payload` 中的 value 允许继续做表达式求值。
- `scope`、`target`、`headers`、`traceId` 不做猜测式表达式执行。
- 路由字段与元数据字段优先强约束，避免消息语义随脚本执行结果漂移。

## 8. 代码迁移落点

### 8.1 Envelope

文件：

- `src/runtime/messaging/envelope.py`

变更：

- 删除 `world_id`
- 引入 `source_world`
- 引入 `target_world`
- 保留 `target`，并把其语义固定为 world 内实例目标

### 8.2 WorldMessageSender

文件：

- `src/runtime/messaging/world_sender.py`

变更：

- 删除 `target_world_id` 参数
- sender 构造时绑定当前 `source_world`
- `send(...)` 只表达“从当前 world 对外发送”
- 出站 envelope 默认：
  - `source_world = self._world_id`
  - `target_world = None`

### 8.3 WorldEventEmitter

文件：

- `src/runtime/world_event_emitter.py`

变更：

- `publish_external(...)` 去掉目标 world 语义
- 对外只暴露：
  - `event_type`
  - `payload`
  - `scope`
  - `target`
  - `trace_id`
  - `headers`

### 8.4 InstanceManager

文件：

- `src/runtime/instance_manager.py`

变更：

- `triggerEvent external=true` 删除 `targetWorldId`
- 保留 `target`
- `payload` 继续按字段求值
- 对 `scope` / `target` / `traceId` / `headers` 做显式结构校验
- 调用 `publish_external(...)` 时不再传目标 world

### 8.5 InboxProcessor / MessageHub

文件：

- `src/runtime/messaging/inbox_processor.py`
- `src/runtime/messaging/hub.py`
- `src/runtime/messaging/sqlite_store.py`

变更：

- worker 级入站路由从 `world_id` 迁移到 `target_world`
- 广播判断改成 `target_world == "*"`
- `target_world is None` 的消息不进入 world 路由

### 8.6 WorldMessageIngress

文件：

- `src/runtime/messaging/world_ingress.py`

变更：

- 不需要改变其主要职责
- 继续把 envelope 转成 world 内部事件
- `envelope.target` 继续作为 world 内实例目标传给 `EventBus`

## 9. 存储迁移

`inbox` / `outbox` 表中的：

- `world_id`

迁移为：

- `source_world`
- `target_world`

保留：

- `target`

这样数据库状态与运行时语义保持一致，不再出现同一字段在不同链路中表达不同含义的问题。

### 9.1 Outbox 语义反转说明

这一轮迁移不只是字段重命名，还包含一处必须显式说明的语义反转：

- 旧设计中，`outbox.world_id` 存的是“目标 world”
- 新设计中，`outbox.source_world` 存的是“来源 world”
- 新设计中的 `outbox.target_world` 对于普通 outward publish 默认是 `null`

也就是说，旧 outbox 记录里的：

- `world_id`

不能直接按“同名迁移”方式映射成：

- `source_world`

否则会把旧数据中的“去向”误读成新数据里的“来源”。

迁移时必须按旧行为语义重新解释：

- 旧 `outbox.world_id` 是旧模型里的目标 world
- 新 `outbox.source_world` 应来自发送时的当前 world
- 新 `outbox.target_world` 对于默认 outward publish 应为 `null`

如果需要做历史数据迁移，必须单独定义旧 outbox 记录的转换策略，不能做机械列映射。

## 10. 测试要求

至少覆盖以下场景：

- `triggerEvent external=true` 不再要求 `targetWorldId`
- outward publish 会写出：
  - `source_world = 当前 world`
  - `target_world = null`
- inbound 定向投递按 `target_world`
- inbound 广播按 `target_world = "*"`
- inbound 消息经过 `Channel -> MessageHub -> InboxProcessor -> WorldMessageIngress -> EventBus` 全链路后，`source_world` 仍被正确保留
- `target` 在 `WorldMessageIngress -> EventBus` 路径中仍表示实例目标
- `scope = scene:sceneId1` 时消息仅在对应 scene 内传播

## 11. 兼容性策略

- 旧字段 `world_id` 视为待迁移字段，不再作为新契约继续扩展。
- 旧 action 字段 `targetWorldId` 直接删除，不提供兼容读取层。
- 所有新测试、新 fixture、新 spec 必须使用：
  - `source_world`
  - `target_world`
  - `target`

## 12. 结论

本设计通过引入：

- `source_world`
- `target_world`
- `target`

三层清晰命名，统一了 outbound / inbound / world 内部事件三种路由语义：

- `source_world / target_world` 负责跨 world 的消息平面语义
- `scope / target` 负责 world 内部事件传播语义

这样 `external=true` 的含义可以稳定收敛为：

**从当前 world 对外发布消息，而不是指定某个目标 world。**
