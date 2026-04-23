# Worker-Supervisor 注册与双向通信设计文档

## 1. 背景与目标

当前 Worker（`agent-studio run`）与 Supervisor 的通信机制存在以下不足：

1. **注册模型偏平**：Worker 以 `world_id` 为单位注册（`notify.runtimeOnline`），一个 Worker 只能管理一个 World，与设计中"Worker 是多 World 容器"的语义不符。
2. **心跳信息匮乏**：心跳仅携带 `world_id` + `session_id`，缺少实例状态、场景列表、World 健康度等关键信息。
3. **Worker 端命令接收不完整**：Worker 的 WebSocket handler 仅注册了 `notify.externalEvent`，未处理 Supervisor 下发的 `world.stop`、`scene.start` 等控制命令。
4. **run-inline 与 run 的通信路径不统一**：`run-inline` 模式下 Supervisor 如何管理 Worker 尚未定义。

本设计目标是建立完善的 **Worker 级注册、心跳、状态汇报和双向命令通信机制**。

---

## 2. 核心概念重新定义

| 概念 | 新定义 |
|---|---|
| **`Worker`** | `agent-studio run` 进程，管理一个或多个 World 的运行时容器。Worker 与 Supervisor 之间是**一对多**的管理关系（一个 Supervisor 管理多个 Worker）。 |
| **`run` 模式** | 真实的 Worker 进程，独立运行，通过 WebSocket 向 Supervisor 注册。 |
| **`run-inline` 模式** | Supervisor 和 WorkerManager 运行在同一进程中，用于本地调试和快速验证。Worker 仍然通过 WebSocket 回环连接注册。 |
| **`WorkerManager`** | Worker 进程内部的管理组件，维护 `world_id -> bundle` 映射，处理 Supervisor 下发的控制命令。 |

**关键变化**：`run` 不再限制为"单 World 进程隔离"，而是"真实 Worker 进程"。`run` 与 `run-inline` 的本质区别是：Worker 是否存在于独立进程中。

---

## 3. Worker 注册模型

### 3.1 Worker 启动注册流程

Worker 启动时自动加载其工作目录下的所有 World，完成初始化后向 Supervisor 发送注册通知：

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
      "started_at": "2026-04-22T10:00:00Z"
    }
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `worker_id` | string | Worker 全局唯一标识，不因 session 变化。由 Worker 在启动时生成，可持久化到 worker 目录。 |
| `session_id` | string | 本次运行会话标识，每次启动重新生成（UUID）。用于区分重连和首次启动。 |
| `world_ids` | list[string] | Worker 当前管理的所有 World ID 列表。 |
| `metadata.pid` | int | Worker 进程 ID。 |
| `metadata.hostname` | string | 主机名。 |
| `metadata.started_at` | string | ISO 8601 时间戳。 |

### 3.2 Supervisor 端注册处理

Supervisor 收到 `notify.worker.activated` 后：

1. 检查 `self._workers` 中是否已有相同 `worker_id`：
   - 若存在旧连接，关闭旧 WebSocket，释放其持有的所有 world 路由。
2. 创建 `WorkerState` 并写入 `self._workers[worker_id]`。
3. 遍历 `world_ids`，更新 `self._world_to_worker[world_id] = worker_id` 映射。
4. 向所有管理客户端广播 `notify.session.reset`，通知客户端该 Worker 会话已重置（通常用于触发 UI 刷新重新订阅状态）：

```json
{
  "jsonrpc": "2.0",
  "method": "notify.session.reset",
  "params": {
    "worker_id": "worker-uuid",
    "world_ids": ["factory-01", "factory-02"]
  }
}
```

### 3.3 Supervisor 端数据结构

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WorkerState:
    worker_id: str
    session_id: str
    ws: WebSocket  # WebSocket 连接对象
    world_ids: list[str]
    metadata: dict  # pid, hostname, started_at
    last_heartbeat: datetime
    status: str  # "active" | "unreachable" | "dead"


class WorkerController:
    def __init__(self, base_dir: str = "worlds"):
        self._base_dir = base_dir
        self._workers: dict[str, WorkerState] = {}  # worker_id -> WorkerState
        self._world_to_worker: dict[str, str] = {}  # world_id -> worker_id
        self._clients: list = []  # 浏览器/管理客户端 WebSocket 列表
        self._lock = asyncio.Lock()
```

### 3.4 命令路由

Supervisor 向 Worker 发送命令时，通过 `world_id` 查找对应 Worker：

```python
async def send_to_worker_by_world(self, world_id: str, message: dict) -> bool:
    worker_id = self._world_to_worker.get(world_id)
    if worker_id is None:
        return False
    worker = self._workers.get(worker_id)
    if worker is None:
        return False
    # 通过 worker.ws 发送 JSON-RPC 消息
    ...
```

---

## 4. 心跳与状态汇报

### 4.1 心跳通知

Worker 每 5 秒发送 `notify.worker.heartbeat`：

```json
{
  "jsonrpc": "2.0",
  "method": "notify.worker.heartbeat",
  "params": {
    "worker_id": "worker-uuid",
    "session_id": "session-uuid",
    "timestamp": "2026-04-22T10:00:05Z",
    "worlds": {
      "factory-01": {
        "status": "loaded",
        "scene_count": 3,
        "instance_count": 15,
        "isolated_scenes": ["sim-01"]
      },
      "factory-02": {
        "status": "error",
        "error": "world.lock: Process 12340 holds lock",
        "scene_count": 0,
        "instance_count": 0
      }
    }
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `timestamp` | string | ISO 8601 时间戳。 |
| `worlds.<id>.status` | string | `loaded` / `starting` / `stopping` / `error`。 |
| `worlds.<id>.error` | string | 可选，status 为 `error` 时的错误信息。 |
| `worlds.<id>.scene_count` | int | 当前运行的场景总数。 |
| `worlds.<id>.instance_count` | int | 当前加载的实例总数。 |
| `worlds.<id>.isolated_scenes` | list[string] | 正在运行的 isolated 场景 ID 列表。 |

### 4.2 Supervisor 端心跳管理

- 维护 `last_heartbeat[worker_id] = timestamp`。
- 超时检测：超过 15 秒未收到心跳，标记 Worker 为 `unreachable`。
- 同机 Worker（本地 spawn）：尝试自动重启进程。
- 远程/边缘 Worker：标记为 `dead`，向客户端广播 `notify.worker.disconnected`。

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

---

## 5. Worker 离线通知

### 5.1 主动离线

Worker 正常停止时发送 `notify.worker.deactivated`：

```json
{
  "jsonrpc": "2.0",
  "method": "notify.worker.deactivated",
  "params": {
    "worker_id": "worker-uuid",
    "session_id": "session-uuid",
    "reason": "shutdown",
    "worlds": {
      "factory-01": {"status": "stopped"},
      "factory-02": {"status": "stopped"}
    }
  }
}
```

**reason 枚举：**

| 值 | 含义 |
|---|---|
| `shutdown` | 正常停止（收到 `world.stop` 或 SIGTERM）。 |
| `crash` | 异常退出（未捕获的异常导致进程崩溃）。 |
| `signal` | 收到 SIGKILL 等强制信号。 |

### 5.2 Supervisor 离线处理

Worker 断开连接时（无论主动还是被动），Supervisor 执行：

1. 从 `self._workers` 移除该 Worker。
2. 遍历该 Worker 的 `world_ids`，从 `self._world_to_worker` 移除。
3. 向所有客户端广播 `notify.worker.disconnected`。

---

## 6. Supervisor → Worker 控制命令

Supervisor 通过 WebSocket 向 Worker 下发 JSON-RPC 请求。Worker 端由 `WorkerManager` 统一处理。

### 6.1 命令列表

| 方法 | 说明 | 参数 |
|---|---|---|
| `world.start` | 让 Worker 加载新 World | `{world_id, world_dir}` |
| `world.stop` | 停止某个 World | `{world_id, force_stop_on_shutdown}` |
| `world.checkpoint` | 立即 checkpoint | `{world_id}` |
| `world.getStatus` | 获取 World 状态 | `{world_id}` |
| `world.reload` | 重新加载 World（热重载模型） | `{world_id}` |
| `scene.start` | 启动 isolated scene | `{world_id, scene_id}` |
| `scene.stop` | 停止 scene | `{world_id, scene_id}` |
| `messageHub.publish` | 向 Worker 的 MessageHub 注入事件 | `{world_id, event_type, payload, source, scope, target}` |

### 6.2 Worker 端处理流程

Worker 收到命令后，由 `WorkerManager` 内部路由：

```python
class WorkerManager:
    def __init__(self):
        self._worlds: dict[str, dict] = {}  # world_id -> bundle

    async def handle_command(self, method: str, params: dict) -> dict:
        world_id = params.get("world_id")
        bundle = self._worlds.get(world_id)
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        
        if method == "world.stop":
            return await self._world_stop(bundle, params)
        elif method == "world.checkpoint":
            return await self._world_checkpoint(bundle, params)
        # ... 其他命令
```

### 6.3 world.stop 处理细节

1. 通过 `WorkerManager` 查找 world_id 对应的 bundle。
2. 调用 `_graceful_shutdown(bundle)`（复用现有逻辑：先停 isolated scenes → 再停 shared scenes → checkpoint → unload → 释放锁）。
3. 从 Worker 的 world 列表移除。
4. 返回 `{"status": "stopped"}`。

**错误码：**

| 错误码 | 含义 |
|---|---|
| `-32001` | World 已被其他 Worker 锁定 |
| `-32002` | Scene 不存在 |
| `-32003` | 非法的生命周期迁移（如 shared scene 独立启停） |
| `-32004` | World 未加载 |

---

## 7. run-inline 模式通信

### 7.1 架构

`run-inline` 模式下，Supervisor 和 WorkerManager 在同一个 Python 进程中运行：

```
[进程内]
  ├── WorkerController (HTTP/WebSocket server)
  │     ├── /workers ←── WebSocket ──→ WorkerManager (同进程)
  │     └── /api/* HTTP API
  └── HTTP server on :8080
```

### 7.2 通信方式

WorkerManager 通过 **WebSocket 回环连接**（`ws://localhost:{supervisor_ws_port}/workers`）向 Supervisor 注册。

- WorkerManager 内部创建 `JsonRpcChannel(ws://localhost:{port}/workers)`。
- 自动重连、心跳、命令处理代码与 `run` 模式完全复用。
- Supervisor 端无需区分"同进程 Worker"和"远程 Worker"，统一按 Worker 处理。

### 7.3 设计理由

- **协议统一**：`run` 和 `run-inline` 使用同一套 JSON-RPC over WebSocket 协议，代码复用率最大化。
- **行为一致**：调试时可以随时将 `run-inline` 切换为真正的 `run` 模式，行为完全一致。
- **可接受的开销**：同进程内走一次 WebSocket 序列化/反序列化，性能开销极小（`run-inline` 本就是调试模式）。

---

## 8. 错误码

| 错误码 | 含义 | 触发场景 |
|---|---|---|
| `-32001` | World 已被其他 Worker 锁定 | Worker 启动时尝试加载已被其他进程锁定的 World |
| `-32002` | Scene 不存在 | `scene.stop` 时 scene_id 找不到 |
| `-32003` | 非法的生命周期迁移 | 尝试独立启停 shared scene；`world.stop` 时存在拒绝停止的 isolated scene 且 `force_stop_on_shutdown=false` |
| `-32004` | World 未加载 | Supervisor 向 Worker 发送命令时，该 World 不在 Worker 的管理列表中 |
| `-32602` | 参数错误 | 缺少必需的参数（如 `scene_id`） |
| `-32601` | 方法未找到 | Worker 收到未注册的 JSON-RPC 方法 |

---

## 9. 设计决策记录

### 决策 1：Worker 级注册替代 World 级注册
- **原因**：Worker 是"多 World 容器"，以 Worker 为管理单元更符合语义。一个 Worker 断开时，其下所有 World 应自动离线。
- **收益**：注册消息数量恒定；Worker 断开时清理逻辑 O(1)；Worker 级元数据（CPU、内存）有自然归属。

### 决策 2：run 不再限制单 World
- **原因**：`run` 与 `run-inline` 的本质区别是"真实 Worker 进程 vs 同进程调试"，而非"单 World vs 多 World"。Worker 进程可以加载多个 World，由 Supervisor 统一管理。
- **收益**：简化概念模型；Worker 进程隔离仍然有效（一个进程内的多个 World 共享进程，但进程崩溃不会影响其他 Worker）。

### 决策 3：run-inline 通过 WebSocket 回环连接
- **原因**：保持协议统一，代码复用最大化。
- **代价**：同进程内走一次序列化/反序列化，性能开销极小（调试场景可接受）。
- **替代方案考虑过**：直接调用 Python API，但需要维护两套调用路径，维护成本高。

### 决策 4：心跳按 Worker 级别发送
- **原因**：Worker 是 Supervisor 的直接管理对象，按 Worker 级别发送心跳更符合层级关系。心跳内嵌每个 World 的摘要状态，满足监控需求。
- **收益**：心跳消息数量不随 World 数量增长；Supervisor 心跳超时检测粒度为 Worker 而非 World。

### 决策 5：WorkerManager 统一管理 World bundle
- **原因**：当前 `run_command.py` 中 bundle 管理散落在函数级别，缺乏统一入口。Supervisor 下发命令需要按 world_id 路由到对应 bundle。
- **收益**：命令路由逻辑内聚；便于后续扩展 Worker 级操作（如 Worker 级 checkpoint）。

---

## 10. 与现有代码的变更点

| 文件 | 变更内容 |
|---|---|
| `src/supervisor/gateway.py` | 重构：`WorkerInfo` → `WorkerState`；`_runtimes` → `_workers` + `_world_to_worker`；新增心跳超时检测；命令路由方法更新 |
| `src/supervisor/server.py` | WebSocket handler 更新：处理 `notify.worker.activated` / `notify.worker.heartbeat` / `notify.worker.deactivated` |
| `src/worker/cli/run_command.py` | 引入 `WorkerManager`；Worker 启动时加载目录下所有 World；WebSocket handler 注册所有 Supervisor 命令 |
| `src/worker/cli/run_inline.py` | 引入 `WorkerManager`；通过 WebSocket 回环连接向 Supervisor 注册 |
| `src/worker/manager.py` (新增) | `WorkerManager` 类：维护 `world_id -> bundle` 映射，处理所有 Supervisor 命令 |
| `src/worker/channels/jsonrpc_channel.py` | 无变更。Worker 作为 client 连接 Supervisor，通过已有 WebSocket 连接接收 Supervisor 下发的命令（反向 RPC）。Worker 端在 `JsonRpcConnection` 上注册命令 handler 即可 |

---

## 11. 后续待设计

- Supervisor HTTP API 的 OpenAPI schema（如 `GET /api/workers`、`GET /api/workers/{worker_id}/worlds` 等）。
- 客户端 SDK 设计与浏览器端订阅/状态同步协议封装。
- Worker 级自动扩容/缩容策略（Supervisor 根据负载自动 spawn 或合并 Worker）。
