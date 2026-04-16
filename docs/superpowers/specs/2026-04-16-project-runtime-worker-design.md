# Project 运行时与隔离架构设计文档

## 1. 背景与目标

当前 `agent-studio` 的 `ProjectRegistry` 在同一个 Python 进程中加载所有 Project，实例间通过独立的 `EventBus`、`InstanceManager` 和脚本 `SandboxExecutor` 实现逻辑隔离。然而：

- 一个 Project 的脚本死循环、内存泄漏或 C 扩展崩溃可能拖垮整个进程。
- 数字孪生类应用需要长期稳定运行，与外部系统（RabbitMQ、OPC-UA 等）保持持久连接。
- 仿真类应用需要频繁启停，对启动速度和资源开销敏感。

本设计目标是：

1. 为需要长期稳定运行的 Project 提供**进程级隔离**。
2. 为临时仿真类 Project 保留**轻量进程内隔离**。
3. 定义统一的通信协议，使 Supervisor、Worker、浏览器客户端使用同一套交互方式。
4. 支持 Worker 在边缘侧**脱离 Supervisor 独立运行**。

---

## 2. 核心概念定义

| 概念 | 定义 |
|---|---|
| **Supervisor** | 可选的管理平面 + WebSocket 网关，负责 `worker` Project 的进程生命周期管理和 `interactive` Project 的进程内托管。 |
| **ProjectWorker** | 承载单个 `worker` 类型 Project 的独立 OS 子进程，具备自举能力。 |
| **worker** | Project 的运行时类型之一，长期运行，不可随意停止，享有进程级隔离。 |
| **interactive** | Project 的运行时类型之二，临时运行，按需启停，在 Supervisor 进程内加载。 |

---

## 3. Project 生命周期类型

`worker` 与 `interactive` **不在 `project.yaml` 中声明**，而是在**启动时**由调用方通过参数指定。Project 文件夹本身与运行时类型解耦，做到真正的"可移植"。

### 3.1 `worker` 类型

- **运行特征**：随启动命令而启动，长期运行，与外部系统持续同步（RabbitMQ、变量数据源）。
- **隔离级别**：**进程级隔离**，每个 `worker` Project 运行在一个独立的 `ProjectWorker` OS 子进程中。
- **停止方式**：仅能通过 Supervisor RPC 或向 Worker 进程发送 SIGTERM 进行优雅停止。
- **适用场景**：数字孪生、与现场产线实时同步的 Project。

### 3.2 `interactive` 类型

- **运行特征**：由用户或 API 按需启动，用于仿真、what-if 分析、培训等场景。
- **隔离级别**：**进程内隔离**，在同一个 Supervisor 进程内通过 `ProjectRegistry` 加载，依赖 Scene/Instance 级逻辑隔离。
- **停止方式**：通过 API 显式调用卸载，停止速度快。
- **适用场景**：临时仿真、快速验证。

## 4. 运行时排他锁

同一个 Project **在同一时间只能以一种 `runtimeType` 被加载**，防止 `worker` 进程与 `interactive` 进程并发写入同一个 `runtime.db`。

### 4.1 锁机制

- **文件锁**：在 Project 目录下创建 `.lock` 文件，使用操作系统文件锁（`fcntl.flock` on Unix / `msvcrt.locking` or `portalocker` on Windows）。
- **锁内容**：JSON 格式，包含 `runtime_type`（`worker` 或 `interactive`）和 `pid`（进程 ID），便于诊断。

```json
{"runtime_type": "worker", "pid": 12345, "started_at": "2026-04-16T10:00:00Z"}
```

### 4.2 获取锁的顺序

无论是 `ProjectWorker` CLI 自举，还是 `ProjectRegistry.load_project()` 加载 `interactive` Project，在打开 `runtime.db` 之前必须：

1. 尝试以**排他模式**获取 `.lock` 文件锁。
2. 若获取失败（文件已被锁定），立即抛出 `RuntimeError("Project {id} is already loaded as {runtime_type} in process {pid}")`。
3. 若获取成功，将本次启动的 `runtime_type` 和 `pid` 写入锁文件。
4. 在 Project 卸载/Worker 退出时，释放锁并（可选）删除 `.lock` 文件。

### 4.3 跨 Supervisor 场景

即使绕过 Supervisor 直接启动 `agent-studio-worker`，文件锁也能阻止另一个 Supervisor 以 `interactive` 模式加载同一个 Project。锁机制是最后一道防线。

---

## 5. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Supervisor Process (可选)                    │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │  interactive   │  │  interactive   │  │   WebSocket      │  │
│  │    Project     │  │    Project     │  │   Gateway/Router │  │
│  │   (in-proc)    │  │   (in-proc)    │  │                  │  │
│  └────────────────┘  └────────────────┘  └────────┬─────────┘  │
│                                                   │             │
│                                                   │ WebSocket   │
└───────────────────────────────────────────────────┼─────────────┘
                                                    │
                                                    │ spawn
                                                    ▼
                                    ┌─────────────────────────────┐
                                    │      ProjectWorker          │
                                    │       (worker)              │
                                    │  ┌───────────────────────┐  │
                                    │  │  ProjectRegistry      │  │
                                    │  │  InstanceManager      │  │
                                    │  │  SceneManager         │  │
                                    │  │  StateManager         │  │
                                    │  │  SQLiteStore          │  │
                                    │  │  RabbitMQ Consumer    │  │
                                    │  │  Variable Adapter     │  │
                                    │  └───────────────────────┘  │
                                    └─────────────────────────────┘
```

- **worker**：Supervisor 仅作为可选的管理平面和网关。Worker 崩溃不影响其他 Project；Supervisor 崩溃也不影响已运行的 Worker。
- **interactive**：直接嵌入调用进程（Supervisor 或本地 CLI），毫秒级启动，适合频繁启停的仿真。`interactive` Project 完全驻留在 Supervisor 内存中，Supervisor 崩溃会导致其丢失，必须由客户端在 Supervisor 重启后重新加载（如需恢复）。

---

## 5. Scene 与 Project 的生命周期关系

| Scene 模式 | 生命周期绑定关系 | 启停方式 |
|---|---|---|
| **`shared`** | **随 Project 一起启动、一起停止** | 自动，不可单独手动启停 |
| **`isolated`** | **依赖 Project 处于运行状态，但可独立启停** | 用户/API 显式控制 |

### 5.1 `shared` Scene

- 是 Project 的"实时视图"，直接引用 Project 全局实例的内存状态。
- `worker` Project 启动时，Worker 自动从 `scenes` 表恢复并启动所有 `shared` Scene。
- `interactive` Project 加载时，由调用方决定是否自动恢复 `shared` Scene（默认自动恢复）。
- Project 停止时，所有 `shared` Scene 必须先停止。
- 对 `shared` Scene 调用 `scene.start` 或 `scene.stop` 应返回 JSON-RPC 错误：`{"code": -32602, "message": "shared scenes cannot be started/stopped independently"}`。

### 5.2 `isolated` Scene

- 是独立的仿真上下文，基于 Project 实例快照创建 CoW 副本。
- 启动 `isolated` Scene 的前提条件：对应 Project 必须已被加载（`interactive`）或 Worker 进程已启动（`worker`）。
- `isolated` Scene 的启停不影响 Project 本身。
- 对于 `interactive` Project，调用 `ProjectRegistry.unload_project()` 时必须先尝试停止所有运行中的 `isolated` Scene。若某 Scene 拒绝停止（取决于 `config.runtime.force_stop_on_shutdown`，见 7.3），则 `unload_project()` 返回 `False` 且继续保留 Project 加载状态；若配置为强制停止，则先停止 Scene 再执行卸载。

---

## 6. 通信协议：统一 WebSocket + JSON-RPC 2.0

所有通信（Supervisor ↔ Worker、Supervisor ↔ 浏览器客户端）统一使用 **WebSocket + JSON-RPC 2.0**。

### 6.1 连接拓扑

- **Supervisor** 作为统一的 WebSocket 网关。
  - `interactive` Project：Supervisor 直接本地处理 JSON-RPC 请求。
  - `worker` Project：Supervisor 将请求通过独立的 WebSocket 转发给对应的 ProjectWorker。
- **浏览器/客户端**：只连接到 Supervisor，由 Supervisor 按 `project_id` 路由。

### 6.2 控制面方法（Request → Response）

| 方法 | 方向 | 说明 |
|---|---|---|
| `project.start` | Supervisor → Worker | 启动 ProjectWorker 进程并加载 project |
| `project.stop` | Supervisor → Worker | 优雅停止，触发 checkpoint 后退出 |
| `project.checkpoint` | Supervisor → Worker | 立即执行一次全量 checkpoint |
| `project.getStatus` | Supervisor → Worker | 返回 Worker 健康状态和实例摘要 |
| `scene.start` | Supervisor → Worker / 本地 | 启动指定 `isolated` Scene |
| `scene.stop` | Supervisor → Worker / 本地 | 停止指定 `isolated` Scene |
| `state.subscribe` | Client → Supervisor | 客户端订阅指定 `project_id` 的实时状态流 |
| `state.unsubscribe` | Client → Supervisor | 客户端取消订阅 |

### 6.3 数据面通知（Notification / One-way）

| 方法 | 方向 | 说明 |
|---|---|---|
| `notify.heartbeat` | Worker → Supervisor | 每 5 秒发送，包含 `project_id`、负载、运行状态 |
| `notify.stateChanged` | Worker → Supervisor/Client | 实例状态变化事件 |
| `notify.eventPublished` | Worker → Supervisor/Client | EventBus 上的业务事件透传 |
| `notify.error` | Worker → Supervisor | Worker 内部异常告警，payload 示例：`{"level": "error", "code": "ADAPTER_CONNECTION_LOST", "message": "...", "instance_id": "...", "timestamp": "2026-04-16T10:00:00Z"}` |

### 6.4 路由规则

Supervisor 收到客户端 WebSocket 消息后，按 `params.project_id` 决定：

1. 若是 `interactive` 且已加载 → 本地 `ProjectRegistry` 调用。
2. 若是 `worker` → 查找对应的 Worker WebSocket 连接并透传。
3. 若 Worker 未连接 → 返回错误 `{"code": -32000, "message": "worker offline"}`。

客户端订阅实时状态时，Supervisor 将对应 Worker 的 `notify.*` 通知**广播**给所有订阅该 `project_id` 的 WebSocket 连接。为避免高频 `metric` 更新淹没连接，实现层可对 `notify.stateChanged` 进行 50–100ms 的批量合并。

#### 会话与重连

每次 ProjectWorker 启动时生成一个 `session_id`（UUID），并在 `notify.workerOnline` 中携带：

```json
{"method": "notify.workerOnline", "params": {"project_id": "steel-plant-01", "session_id": "uuid-v4"}}
```

- Supervisor 用 `session_id` 区分新旧连接，收到新的 `workerOnline` 后应使旧连接的订阅失效，并向客户端发送 `notify.sessionReset`。
- 客户端在收到 `notify.sessionReset` 后应重新订阅所需的状态流。

---

## 7. ProjectWorker 进程模型

### 7.1 启动命令

通过 `pyproject.toml` 注册自定义 CLI：

```toml
[project.scripts]
agent-studio-worker = "src.runtime.worker.cli:main"
```

使用示例：

```bash
# 独立运行
agent-studio-worker --project-dir=projects/steel-plant-01

# 带 Supervisor
agent-studio-worker --project-dir=projects/steel-plant-01 \
                    --supervisor-ws=ws://localhost:8001/workers
```

### 7.2 启动顺序

1. **解析 CLI 参数**：读取 `--project-dir`、`--supervisor-ws`（可选）。
2. **连接 Supervisor WebSocket**（若提供）：发送 `notify.workerOnline`，携带 `project_id`。
3. **获取运行时排他锁**：在 Project 目录下获取 `.lock` 文件锁，写入 `"runtime_type": "worker"`。若已被占用，立即退出并报错。
4. **加载 Project**：调用 `ProjectRegistry.load_project(project_id)`。
5. **恢复状态**：`StateManager.restore_project()` → 加载实例快照 + 重放事件日志。
6. **自动启动 `shared` Scenes**：遍历 `scenes` 表中记录的运行时 `shared` Scene，调用 `SceneManager.start(..., mode="shared")`。
7. **启动外部适配器**：
   - RabbitMQ Consumer 开始监听该 Project 的业务事件队列。
   - Variable Adapter 按配置连接 OPC-UA / MQTT / REST 等数据源。
8. **进入主循环**：处理 WebSocket RPC 请求、消费 RabbitMQ 消息、向 Supervisor 发心跳。

### 7.3 优雅停止顺序

1. 收到 `project.stop` RPC 或 **SIGTERM**。
2. 停止外部适配器：关闭 RabbitMQ 连接和数据源订阅。
3. 停止 `isolated` Scenes：如果有正在运行的 `isolated` Scene：
   - 默认策略：先停止它们再关闭 Project。
   - 若配置为 `config.runtime.force_stop_on_shutdown: false`，则拒绝停止请求。
   - 配置默认值：以 `worker` 启动时为 `false`，以 `interactive` 启动时为 `true`。
4. 禁用自动 checkpoint：先将 `project_id` 从 `StateManager` 的 `loaded_projects` 中移除，并获取 per-project 锁以确保后台线程不会并发执行 checkpoint。
5. 停止 `shared` Scenes。
6. 执行最终 checkpoint：`StateManager.checkpoint_project()`。
7. 卸载 Project：`ProjectRegistry.unload_project(project_id)`。
8. 释放运行时排他锁并删除 `.lock` 文件。
9. 发送 `notify.workerOffline`，断开 WebSocket。
10. 进程退出。

### 7.4 异常退出与恢复

如果 ProjectWorker 因异常崩溃，Supervisor 在心跳超时（默认 15 秒）后检测到失联，根据配置策略执行：

- **自动重启**（默认）：重新启动 ProjectWorker 进程，依赖 `StateManager.restore_project()` 恢复状态。
- **告警但不重启**：等待人工介入。

---

## 8. 独立运行与边缘部署

ProjectWorker 是**自包含**的，可以脱离 Supervisor 独立运行。

### 8.1 无 Supervisor 模式

未提供 `--supervisor-ws` 时：

- `SupervisorClient` 不被实例化。
- 控制指令通过 **SIGTERM** 触发优雅停止 + 最终 checkpoint。
- 状态通过本地日志输出，不发送心跳。
- 可选开启本地 WebSocket 端口（如 `--ws-port=9001`）供浏览器直接连接。生产环境必须配合带外认证机制（如 mTLS 反向代理、API Token 子协议），不建议直接暴露无认证端口。

### 8.2 边缘侧最小文件清单

```
/opt/agent-studio/
├── agent_studio/              # Python 包
│   ├── runtime/
│   │   ├── worker/            # Worker 专属模块
│   │   │   ├── __init__.py
│   │   │   ├── cli.py         # 命令行入口
│   │   │   ├── runtime.py     # WorkerRuntime
│   │   │   └── supervisor_client.py  # 可选 SupervisorClient
│   │   ├── event_bus.py
│   │   ├── instance.py
│   │   ├── instance_manager.py
│   │   ├── scene_manager.py
│   │   ├── state_manager.py
│   │   ├── project_registry.py
│   │   ├── persistent_event_bus.py
│   │   ├── model_loader.py
│   │   ├── metric_store.py
│   │   ├── stores/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── sqlite_store.py
│   │   ├── lib/
│   │   │   ├── __init__.py
│   │   │   ├── registry.py
│   │   │   ├── sandbox.py
│   │   │   ├── proxy.py
│   │   │   ├── decorator.py
│   │   │   ├── watcher.py
│   │   │   └── exceptions.py
│   │   └── adapters/          # 数据源适配器（新增）
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── mqtt_adapter.py
│   │       ├── opcua_adapter.py
│   │       └── rest_adapter.py
│   └── __init__.py
├── projects/<project-id>/     # 项目数据目录
│   ├── project.yaml
│   ├── runtime.db
│   ├── scenes/
│   └── resources/
├── agents/                    # Agent 静态模型定义
│   └── ...
├── pyproject.toml
└── requirements.txt
```

边缘启动示例：

```bash
agent-studio-worker \
  --project-dir=/opt/agent-studio/projects/steel-plant-01 \
  --agents-dir=/opt/agent-studio/agents
```

---

## 9. 与现有代码的兼容性

- `ProjectRegistry`、`InstanceManager`、`SceneManager`、`StateManager`、`SQLiteStore` 等核心代码**直接复用**。
- `SandboxExecutor` 继续作为脚本安全层生效；进程级隔离提供额外的故障隔离。
- 新增模块主要集中在 `src/runtime/worker/`（Worker 运行时）和 `src/runtime/adapters/`（外部数据源适配器）。

---

## 10. 设计决策记录

### 决策 1：worker / interactive 双类型由启动时声明
- **原因**：数字孪生需要长期稳定运行和强隔离，而仿真需要快速启停和低资源开销。一种运行时模型无法同时满足两种诉求。将运行时类型从 `project.yaml` 中移除、改为启动参数，使 Project 文件夹与部署方式解耦，同一个 Project 可以在开发环境以 `interactive` 调试、在生产环境以 `worker` 常驻运行。

### 决策 2：统一 WebSocket + JSON-RPC 2.0 协议
- **原因**：客户端（浏览器、移动端、第三方系统）对 WebSocket 和 JSON 的原生支持最好，不需要引入 gRPC 的 protobuf 依赖。

### 决策 3：Worker 支持自举运行
- **原因**：开发调试时需要快速启动单个 Project；边缘部署时不宜强制依赖 Supervisor。

### 决策 4：shared Scene 随 Project 一起启停
- **原因**：`shared` Scene 直接引用 Project 全局实例的内存状态，没有独立的生命周期意义。Project 停止后，shared Scene 自然失效。

### 决策 5：isolated Scene 手动启停但依赖 Project 已加载
- **原因**：`isolated` Scene 使用 CoW 副本，需要基于 Project 实例池创建，但仿真上下文本身具有独立的管理需求（如用户手动开始/结束一次演练）。

### 决策 6：运行时排他锁防止并发加载
- **原因**：`worker` 与 `interactive` 都持有 `runtime.db` 的写连接，若同一 Project 被同时以两种类型加载，会导致数据损坏。文件锁是最简单且跨 Supervisor/CLI 生效的防御手段。

---

## 11. 后续待设计事项

- `src/runtime/worker/` 的详细类接口设计（`WorkerRuntime`、`SupervisorClient`、`CLI`）。
- `src/runtime/adapters/` 的适配器基类与数据源配置 schema。
- `src/runtime/locks/` 或 `ProjectLock` 的跨平台文件锁实现（Windows / Linux）。
- Supervisor 的 HTTP/WebSocket 网关接口与客户端 SDK 设计。
- Worker 进程健康检查、自动重启策略的详细配置。
