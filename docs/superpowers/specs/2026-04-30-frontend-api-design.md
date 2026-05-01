# Frontend API 设计文档

> 日期：2026-04-30  
> 范围：管理控制台 + 实时状态看板（MVP）

---

## 1. 背景与目标

为 agent-studio 系统设计一套前端 API，使前端界面能够通过 Supervisor 统一网关管理和监控系统状态。

**核心约束**：Supervisor 与 Worker 可跨网络部署，Worker 可能位于内网或边缘设备，前端无法直接访问 Worker。

**目标**：
1. 前端只与 Supervisor 通信，不感知 Worker 的存在和位置。
2. 提供完整的查询能力（workers、worlds、models、instances、scenes）。
3. 提供实时状态推送（WebSocket），无需前端轮询。
4. 提供控制操作（启停 world/scene、触发 checkpoint）。

---

## 2. 架构设计

### 2.1 通信模型

```
┌─────────┐   REST API     ┌─────────────┐   JSON-RPC/WS    ┌─────────┐
│         │ ◄────────────► │             │ ◄──────────────► │         │
│  前端   │                │  Supervisor │                  │  Worker │
│         │   WebSocket    │             │                  │         │
│         │ ◄────────────► │             │                  │         │
└─────────┘                └─────────────┘                  └─────────┘
```

- **REST API**：前端通过 HTTP 查询状态和发起操作（请求-响应模式）。
- **WebSocket (`/ws`)**：仅用于 Supervisor 向前端推送实时通知（单向）。
- **Supervisor → Worker**：通过已有的 WebSocket 连接发送 JSON-RPC 请求并等待响应。

### 2.2 为什么命令不走 WebSocket

- REST API 有成熟的错误处理、超时控制、重试和负载均衡。
- Supervisor 不需要维护 `client_ws + req_id → future` 的复杂映射。
- 前端代码更简单（标准 fetch 而非 WebSocket 状态机）。
- WebSocket 仅保留给服务端主动推送场景（心跳、状态变化）。

---

## 3. REST API 设计

### 3.1 通用约定

**分页参数**（列表接口）：
- `?limit=` — 每页数量，默认 100，最大 1000
- `?offset=` — 偏移量，默认 0

**字段裁剪**（列表接口）：
- `?fields=` — 逗号分隔的字段名，如 `?fields=instance_id,model_name,state`

**字段命名映射**：
Worker 的 JSON-RPC 响应使用 `id`（而非 `instance_id`）和 `model`（而非 `model_name`）。Supervisor 的 REST 层负责将 Worker 字段名映射为前端统一的命名规范。详见第 6.1 节。

**错误响应**：
```json
{
  "error": "error_code",
  "message": "Human-readable description"
}
```

### 3.2 Workers

#### GET /api/workers

列出所有已注册的 workers。

**响应**：
```json
{
  "items": [
    {
      "worker_id": "worker-uuid",
      "session_id": "session-uuid",
      "world_ids": ["factory-01", "factory-02"],
      "metadata": {
        "pid": 12345,
        "hostname": "edge-server-01",
        "started_at": "2026-04-30T10:00:00Z"
      },
      "status": "active"
    }
  ],
  "total": 1
}
```

### 3.3 Worlds

#### GET /api/workers/{worker_id}/worlds

列出某个 worker 下的所有 worlds。

**响应**：
```json
{
  "items": [
    {
      "world_id": "factory-01",
      "status": "running",
      "scene_count": 3,
      "instance_count": 15
    }
  ],
  "total": 1
}
```

#### GET /api/worlds/{world_id}

获取 world 详情。

**响应**：
```json
{
  "world_id": "factory-01",
  "worker_id": "worker-uuid",
  "status": "running",
  "scenes": ["scene-01", "scene-02", "scene-03"],
  "instance_count": 15
}
```

**实现说明**：`instance_count` 由 Supervisor 在代理此请求时，内部调用 Worker 的 `world.instances.list` 命令计算 `len(instances)` 后填入响应。Supervisor 缓存此结果用于变化检测（见 4.3 节 `notify.world.status_changed`）。

#### POST /api/worlds/{world_id}/start

启动 world。若 world 已在运行，返回 `{"status": "already_running"}`。

**响应**：
```json
{"status": "starting"}
```

#### POST /api/worlds/{world_id}/stop

停止 world。向对应 Worker 发送 `world.stop` 命令。

**响应**：
```json
{"status": "stop_requested"}
```

#### POST /api/worlds/{world_id}/checkpoint

触发 world checkpoint。向对应 Worker 发送 `world.checkpoint` 命令。

**响应**：
```json
{"status": "checkpointed"}
```

### 3.4 Models

**注意**：Worker 当前没有 model 查询相关的 JSON-RPC 命令。实现此 API 需要以下两种方案之一：

**方案 A（推荐）**：在 Worker 上新增 `world.models.list` 和 `world.models.get` JSON-RPC 命令。Worker 通过 world bundle 中的 `world_dir` 字段定位到 world 目录，再扫描 `{world_dir}/agents/` 下的子目录，用 `ModelLoader` 读取每个 `agents/{model_id}/model/` 目录的模型定义。

**方案 B**：Supervisor 通过扫描 `worlds/{world_id}/agents/` 目录直接读取模型文件，不经过 Worker。此方案仅适用于 Supervisor 与 world 目录同机部署的场景。

本规范按方案 A 设计，确保跨网络场景可用。

#### GET /api/worlds/{world_id}/models

列出 world 下的所有 model 定义。

**响应**：
```json
{
  "items": [
    {
      "model_id": "robot",
      "metadata": {
        "name": "Robot Agent",
        "version": "1.0"
      }
    }
  ],
  "total": 1
}
```

#### GET /api/worlds/{world_id}/models/{model_id}

获取 model 详情，包含完整的模型定义。

**响应**（字段与 `ModelLoader.load()` 返回结构一致）：
```json
{
  "model_id": "robot",
  "metadata": {"name": "Robot Agent", "version": "1.0"},
  "attributes": {
    "type": {"type": "string", "default": "agv"}
  },
  "variables": {
    "speed": {"type": "number", "default": 0}
  },
  "behaviors": [
    {
      "trigger": {"event": "order.created"},
      "actions": [{"type": "runScript", "script": "..."}]
    }
  ],
  "events": {
    "order.created": {"params": [{"name": "order_id", "type": "string"}]}
  },
  "states": ["idle", "busy", "error"],
  "transitions": [
    {"from": "idle", "to": "busy", "event": "order.created"}
  ],
  "derivedProperties": {},
  "links": {},
  "functions": {},
  "services": {},
  "alarms": {},
  "schedules": {},
  "goals": {},
  "decisionPolicies": {},
  "memory": {},
  "plans": {}
}
```

**说明**：具体字段取决于 model 定义文件。`ModelLoader.load()` 读取 `agents/{model_id}/model/index.yaml` 及其分片文件，返回的 dict 键与文件结构一致。REST 层直接透传，不做字段转换。

### 3.5 Instances

#### GET /api/worlds/{world_id}/instances

列出 world 下的所有 instances，支持过滤。

**过滤参数**：
- `?model_id=` — 按 model 过滤
- `?scope=` — 按 scope 过滤（`world` 或 `scene:{scene_id}`）
- `?lifecycle_state=` — 按生命周期状态过滤（`active`、`archived` 等）
- `?state=` — 按当前状态过滤

过滤由 Supervisor 在收到 Worker 的全量列表后在内存中执行，减少 Worker 侧改动。

**响应**：
```json
{
  "items": [
    {
      "instance_id": "inst-01",
      "model_name": "robot",
      "scope": "world",
      "state": "idle",
      "lifecycle_state": "active",
      "variables": {"speed": 10},
      "attributes": {"type": "agv"}
    }
  ],
  "total": 1
}
```

**字段映射说明**：Worker 的 `world.instances.list` 返回 `id`（映射为 `instance_id`）和 `model`（映射为 `model_name`），`state` 返回字典但列表响应中只取 `state.current`。

#### GET /api/worlds/{world_id}/instances/{instance_id}

获取单个 instance 详情。

**实现说明**：Worker 当前没有 `world.instances.get` JSON-RPC 命令。实现此端点需要新增该命令，由 `InstanceManager` 按 `instance_id` 查找并返回完整 instance 数据（包括 `state` 字典、`bindings`、`links`、`memory`、`audit` 等字段）。若未找到返回 `-32004`。

**响应**：
```json
{
  "instance_id": "inst-01",
  "model_name": "robot",
  "scope": "world",
  "state": {"current": "idle", "entered_at": "2026-04-30T10:00:00Z"},
  "lifecycle_state": "active",
  "variables": {"speed": 10},
  "attributes": {"type": "agv"},
  "bindings": {},
  "links": {},
  "memory": {},
  "audit": {"version": 5, "updated_at": "2026-04-30T10:05:00Z", "last_event_id": "evt-42"}
}
```

### 3.6 Scenes

#### GET /api/worlds/{world_id}/scenes

列出 world 下的所有 scenes。

**实现说明**：Worker 当前没有返回 scene 元数据（`mode`、`instance_count`）的 JSON-RPC 命令。实现此端点需要新增 `world.scenes.list` 命令，由 `SceneManager` 返回每个 scene 的 `scene_id`、`mode` 和该 scene 下的 instance 数量。

**响应**：
```json
{
  "items": [
    {
      "scene_id": "scene-01",
      "mode": "shared",
      "instance_count": 5
    },
    {
      "scene_id": "sim-01",
      "mode": "isolated",
      "instance_count": 3
    }
  ],
  "total": 2
}
```

#### GET /api/worlds/{world_id}/scenes/{scene_id}/instances

获取场景下的实例列表。自动按 `scope=scene:{scene_id}` 过滤。

支持同样的过滤参数：`?model_id=`、`?lifecycle_state=`、`?state=`。

**响应**：同 `/api/worlds/{world_id}/instances`。

#### POST /api/worlds/{world_id}/scenes/{scene_id}/start

启动 isolated scene。向 Worker 发送 `scene.start` 命令。

**响应**：
- 成功：`{"status": "started"}`
- 已在运行：`{"status": "already_running"}`

#### POST /api/worlds/{world_id}/scenes/{scene_id}/stop

停止 scene。向 Worker 发送 `scene.stop` 命令。

**响应**：
- 成功：`{"status": "stopped"}`
- Scene 不存在：`404` + `{"error": "scene_not_found", "message": "Scene not found"}`

---

## 4. WebSocket 推送协议

### 4.1 连接

前端连接 `ws://supervisor/ws`。

### 4.2 推送消息格式

所有推送消息使用 JSON-RPC notification 格式（无 `id` 字段）：

```json
{
  "jsonrpc": "2.0",
  "method": "notify.xxx",
  "params": {...}
}
```

### 4.3 推送类型

#### notify.worker.activated

Worker 上线时推送。

```json
{
  "jsonrpc": "2.0",
  "method": "notify.worker.activated",
  "params": {
    "worker_id": "worker-uuid",
    "session_id": "session-uuid",
    "world_ids": ["factory-01", "factory-02"],
    "metadata": {
      "pid": 12345,
      "hostname": "edge-server-01",
      "started_at": "2026-04-30T10:00:00Z"
    }
  }
}
```

#### notify.worker.heartbeat

Worker 心跳，每 5 秒推送一次。

```json
{
  "jsonrpc": "2.0",
  "method": "notify.worker.heartbeat",
  "params": {
    "worker_id": "worker-uuid",
    "session_id": "session-uuid",
    "timestamp": "2026-04-30T10:00:05Z",
    "worlds": {
      "factory-01": {
        "status": "running",
        "scene_count": 3,
        "instance_count": 15
      }
    }
  }
}
```

#### notify.worker.disconnected

Worker 断开时推送。

```json
{
  "jsonrpc": "2.0",
  "method": "notify.worker.disconnected",
  "params": {
    "worker_id": "worker-uuid",
    "world_ids": ["factory-01", "factory-02"],
    "reason": "heartbeat_timeout"
  }
}
```

#### notify.world.status_changed

World 状态变化时推送。

**生成方式**：Supervisor 缓存每个 worker 心跳中的 world 状态，当检测到 `status` 字段变化时生成此通知。也在 REST API 命令（如 `world.stop`）成功执行后推送。

```json
{
  "jsonrpc": "2.0",
  "method": "notify.world.status_changed",
  "params": {
    "world_id": "factory-01",
    "status": "stopped",
    "previous_status": "running",
    "reason": "user_request"
  }
}
```

#### notify.instance.state_changed（后续扩展）

Instance 状态变化时推送。

**MVP 阶段不实现**。Worker 当前不主动上报 instance 状态变化。后续实现方案：
- 方案 A：Worker 扩展 `EventBus`，在 instance 状态变化时向 Supervisor 推送 `notify.instance.stateChanged`。
- 方案 B：Supervisor 周期性缓存 `world.instances.list` 结果，对比差异后生成通知。

MVP 阶段前端通过主动刷新 instance 列表获取最新状态。

```json
{
  "jsonrpc": "2.0",
  "method": "notify.instance.state_changed",
  "params": {
    "world_id": "factory-01",
    "instance_id": "inst-01",
    "state": "idle",
    "previous_state": "busy"
  }
}
```

### 4.4 广播策略

所有已连接客户端收到同样的推送消息，**不做订阅过滤**。理由：
- 系统规模小（worker 数量、world 数量、前端客户端数量均有限）。
- 心跳数据量小（每 5 秒一次）。
- 实现简单，Supervisor 不需要维护订阅表。

前端自行根据 `world_id` 或 `worker_id` 过滤。

---

## 5. 错误处理

### 5.1 JSON-RPC 错误码映射

Supervisor 将 Worker 返回的 JSON-RPC 错误码映射为 HTTP 状态码：

| Worker 错误码 | HTTP 状态码 | 含义 |
|---|---|---|
| `-32004` (World not loaded) | `404` | World 不存在或未加载 |
| `-32002` (Scene not found) | `404` | Scene 不存在 |
| `-32003` (Illegal lifecycle) | `409` | 状态冲突 |
| `-32001` (World locked) | `409` | World 被其他 Worker 锁定 |
| `-32602` (Invalid params) | `400` | 参数错误 |
| `-32601` (Method not found) | `501` | 功能未实现 |
| Worker 不可达 | `502` | 网关错误 |
| Worker 超时 | `504` | 网关超时 |

### 5.2 错误响应体

```json
{
  "error": "error_code",
  "message": "Human-readable description"
}
```

示例：
```json
{
  "error": "world_not_found",
  "message": "World factory-01 is not loaded on any worker"
}
```

---

## 6. 数据格式约定

### 6.1 命名规范

沿用现有代码的 `snake_case`：
```json
{"instance_id": "inst-01", "model_name": "robot", "lifecycle_state": "active"}
```

### 6.2 时间格式

ISO 8601 UTC：
```json
{"started_at": "2026-04-30T12:00:00Z"}
```

---

## 7. 认证（MVP 后考虑）

MVP 阶段暂不实现认证（假设内网部署）。

后续如需暴露到公网，采用简单 Bearer Token 方案：
- `Authorization: Bearer <token>`
- Token 通过环境变量 `SUPERVISOR_API_TOKEN` 配置。
- Worker → Supervisor 的 WebSocket 注册增加 `auth_token` 字段校验。

---

## 8. 设计决策记录

### 决策 1：Supervisor 作为统一网关
- **原因**：Worker 可跨网络部署（内网/边缘），前端通常无法直接访问 Worker。
- **收益**：前端只需配置 Supervisor 地址；安全边界清晰；Worker 不需要暴露公网端口。
- **代价**：Supervisor 成为流量瓶颈和单点（可通过多 Supervisor 实例+负载均衡缓解）。

### 决策 2：WebSocket 只做推送，命令走 REST API
- **原因**：REST API 有成熟的错误处理、超时控制；Supervisor 无需维护复杂的请求-响应映射；前端代码更简单。
- **收益**：降低 Supervisor 实现复杂度；前端使用标准 fetch/axios 即可。
- **代价**：实时命令的延迟略高于 WebSocket（多一次 HTTP 握手，对管理控制台可接受）。

### 决策 3：WebSocket 全量广播，无订阅过滤
- **原因**：系统规模小，心跳数据量有限，广播实现最简单。
- **收益**：Supervisor 不需要维护订阅表；客户端连接/断开逻辑简单。
- **代价**：客户端收到少量无关数据，自行过滤。规模扩大后需要引入订阅机制。

### 决策 4：Worker JSON-RPC 错误码映射为 HTTP 状态码
- **原因**：前端使用标准 HTTP 工具链，JSON-RPC 错误码对前端不透明。
- **收益**：前端可按标准 HTTP 语义处理错误（404=资源不存在，502=后端不可用）。

---

## 9. 与现有代码的变更点

| 文件 | 变更内容 |
|---|---|
| `src/supervisor/server.py` | 新增 REST API 路由（`/api/workers/{worker_id}/worlds`、`/api/worlds/{world_id}/instances` 等）；WebSocket `/ws` 保持全量广播 |
| `src/supervisor/worker.py` | 新增/复用 `send_request` 用于同步等待 Worker 响应；HTTP handler 调用此方法代理请求；缓存 world 状态用于变化检测 |
| `src/worker/manager.py` | 在 `handle_command` 中新增 `world.models.list`、`world.models.get`、`world.instances.get`、`world.scenes.list` 命令处理逻辑 |
| `src/worker/cli/run_command.py` | 在 `_register_worker_handlers` 中注册新增的 JSON-RPC handler（`world.models.list`、`world.models.get`、`world.instances.get`、`world.scenes.list`）|

---

## 10. 后续扩展

- 认证与授权（Bearer Token / OAuth2）
- WebSocket 订阅机制（按 world_id 过滤，减少无关流量）
- 事件历史查询（`GET /api/worlds/{world_id}/events`）
- 批量操作 API（批量启停 instances）
- 指标与监控（Prometheus metrics）
