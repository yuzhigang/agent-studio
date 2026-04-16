# Project 运行时与隔离架构设计文档

## 1. 背景与目标

当前 `agent-studio` 的 `ProjectRegistry` 在同一个 Python 进程中加载所有 Project，实例间通过独立的 `EventBus`、`InstanceManager` 和脚本 `SandboxExecutor` 实现逻辑隔离。然而：

- 一个 Project 的脚本死循环、内存泄漏或 C 扩展崩溃可能拖垮整个进程。
- 数字孪生类应用需要长期稳定运行，与外部系统（RabbitMQ、OPC-UA 等）保持持久连接。
- 仿真类应用需要频繁启停，对启动速度和资源开销敏感。

本设计目标是：

1. 为需要长期稳定运行的 Project 提供**进程级隔离**。
2. 为临时仿真类 Project 保留**轻量进程内隔离**。
3. 定义统一的通信协议，使 Supervisor、运行时进程、浏览器客户端使用同一套交互方式。
4. 支持运行时进程在边缘侧**脱离 Supervisor 独立运行**。

---

## 2. 核心概念定义

| 概念 | 定义 |
|---|---|
| **`ProjectRuntime`** | `agent-studio` 的运行时进程，内部持有 `ProjectRegistry`，负责加载 Project、运行实例、消费外部事件。 |
| **Supervisor** | 可选的管理平面 + WebSocket 网关，负责管理多个 `ProjectRuntime` 进程的生命周期和请求路由。 |

### 关键设计原则

- **一个 `ProjectRuntime` 进程可以加载多个 Project**（代码能力上）。
- 但在**生产隔离架构**下，我们**约束每个 `ProjectRuntime` 进程只加载一个 Project**，以获得最强的故障隔离。
- `ProjectRuntime` 与 `Supervisor` 之间是**可选的管理关系**，不是运行时必需依赖。

---

## 3. 统一 CLI 设计

所有运行模式通过 `agent-studio` 一个入口暴露，使用子命令区分：

### 3.1 `agent-studio run` — 单 Project 隔离模式

```bash
# 独立运行（边缘部署）
agent-studio run --project-dir=projects/steel-plant-01

# 独立运行 + 本地 WebSocket（供浏览器直连）
agent-studio run --project-dir=projects/steel-plant-01 --ws-port=9001

# 连接 Supervisor，接受集中管理
agent-studio run --project-dir=projects/steel-plant-01 \
                  --supervisor-ws=ws://localhost:8001/workers
```

- **进程模型**：当前进程**只加载一个 Project**。
- **隔离级别**：**进程级隔离**。
- **适用场景**：生产环境、数字孪生、边缘部署。
- **参数约束**：`--project-dir` 在此子命令下只能出现**一次**。传入多次应报错。

### 3.2 `agent-studio run-inline` — 多 Project 内联模式

```bash
agent-studio run-inline \
  --project-dir=projects/factory-01 \
  --project-dir=projects/factory-02 \
  --project-dir=projects/factory-03
```

- **进程模型**：当前进程内加载多个 Project。
- **隔离级别**：**线程/内存级隔离**（共享同一个 Python 进程）。
- **适用场景**：开发调试、集成测试、本地快速验证。
- **参数约束**：`--project-dir` 在此子命令下可出现**一次或多次**，每次指定一个 Project 目录。

### 3.3 `agent-studio supervisor` — 管理平面

```bash
agent-studio supervisor \
  --base-dir=projects \
  --ws-port=8001 \
  --http-port=8080
```

- **进程模型**：Supervisor 自身**不加载任何 Project**，只负责管理子进程和网关路由。
- **适用场景**：集中管理多个 Project 的生产环境。

---

## 4. 运行时排他锁

同一个 Project **在同一时间只能被一个 `ProjectRuntime` 进程加载**，防止多个进程并发写入同一个 `runtime.db`。

### 4.1 锁机制

- **文件锁**：在 Project 目录下创建 `.lock` 文件，使用操作系统文件锁。
- **锁内容**：JSON 格式，包含 `pid`（进程 ID）和 `started_at`，便于诊断。

```json
{"pid": 12345, "started_at": "2026-04-16T10:00:00Z"}
```

### 4.2 获取锁的顺序

无论是 `agent-studio run` 还是 `agent-studio run-inline`，在打开 `runtime.db` 之前必须：

1. 打开（或创建）`.lock` 文件。
2. 尝试以**非阻塞排他模式**获取文件锁。
3. 若获取失败：
   - 读取 `.lock` 文件中已有的 JSON 内容，提取 `pid`。
   - 抛出 `RuntimeError("Project {id} is already loaded in process {pid}")`。
   - 若文件内容不可读，回退为通用错误 `RuntimeError("Project {id} is already locked")`。
4. 若获取成功，立即将 `pid` 写入锁文件并 `flush`。
5. 在 Project 卸载/进程退出时，释放锁并删除 `.lock` 文件。

### 4.3 过期锁恢复

- **Unix**：`fcntl.flock` 是进程绑定的建议锁，进程崩溃后锁自动释放。`.lock` 文件残留不会阻塞后续启动，启动时直接覆盖即可。
- **Windows**：启动逻辑应读取锁文件中的 `pid`，检查该 PID 是否仍在运行。若 PID 已不存在，允许覆盖并获取锁；若仍在运行，则报错。为降低 PID 复用导致的误判风险，可补充进程启动时间比对等启发式校验，或直接使用 `filelock` / `fasteners` 等基于操作系统原语的库来避免手动 PID 检查。
- **推荐实现**：封装跨平台 `ProjectLock` 工具类，优先使用 `fasteners` 或 `filelock` 等成熟库。
- **Windows 特殊处理**：`fasteners` 的 `InterProcessLock` 会直接锁定文件句柄，导致无法同时向该文件写入 JSON 元数据。实现上采用**双文件方案**：`.lockfile` 作为 OS 级互斥锁的载体，`.lock` 仅用于存储 JSON 元数据（`pid`、`started_at`），这样 Windows 下既能获得进程级排他锁，又能保留可读的诊断信息。

---

## 5. 不同场景下的 Project 启停方式

### 5.1 场景一：本地单机部署（Supervisor 直接 spawn）

**启动流程：**
1. 客户端向 Supervisor 发送 HTTP/WebSocket 请求：`POST /api/projects/{id}/start`
2. Supervisor 本地 `spawn` 子进程：
   ```bash
   agent-studio run --project-dir=projects/{id} --supervisor-ws=ws://localhost:8001/workers
   ```
3. 子进程启动后，主动通过 WebSocket 连接 Supervisor，发送 `notify.runtimeOnline`。
4. Supervisor 将该 WebSocket 连接与 `{id}` 绑定，确认就绪。

**停止流程：**
1. 客户端向 Supervisor 发送 `POST /api/projects/{id}/stop`
2. Supervisor 通过 WebSocket 向该子进程发送 `project.stop` JSON-RPC。
3. 子进程执行优雅停止（checkpoint → 释放锁 → 退出）。
4. 若子进程无响应，Supervisor 可发送 `SIGTERM`，必要时 `SIGKILL`。

### 5.2 场景二：边缘服务器部署（反向注册）

**启动流程：**
1. 边缘服务器由外部编排系统（systemd / Docker / k8s）执行：
   ```bash
   agent-studio run --project-dir=/opt/projects/{id} --supervisor-ws=ws://central-supervisor:8001/workers
   ```
2. `agent-studio run` 启动后，主动通过 WebSocket 反向注册到中央 Supervisor，发送 `notify.runtimeOnline`。
3. Supervisor 确认连接，将该 runtime 与 `{id}` 绑定。

**停止流程（优雅）：**
1. 客户端向 Supervisor 发送 `POST /api/projects/{id}/stop`
2. Supervisor 通过 WebSocket 发送 `project.stop` JSON-RPC。
3. 边缘子进程执行优雅停止并退出。

**停止流程（强制）：**
- Supervisor **无法跨网络发送 SIGTERM 或 SIGKILL**。
- 若子进程对 `project.stop` 无响应，Supervisor 只能：
  1. 标记该 Project 为 "unreachable" 或 "dead"。
  2. 向客户端返回错误，提示需要边缘运维系统介入。
  3. 边缘的 systemd / Docker / k8s 负责实际的发信号和重启。

> **核心边界**：Supervisor 的远程控制能力止于 WebSocket。进程级别的强制终止必须依赖边缘侧的本地编排系统。

### 5.3 场景三：开发调试（run-inline）

**启动流程：**
1. 开发者在本地直接执行：
   ```bash
   agent-studio run-inline --project-dir=projects/factory-01 --project-dir=projects/factory-02
   ```
2. 当前进程内依次加载多个 Project，各自持有独立的 `EventBus` 和 `SQLiteStore`。
3. 无 Supervisor，控制通过本地 JSON-RPC over HTTP 或裸 Python API 完成。

**停止流程：**
1. 发送 SIGINT / SIGTERM 给当前进程。
2. 进程按加载顺序反向逐个停止 Project（先 isolated scenes → 再 shared scenes → checkpoint → 释放锁 → unload）。
3. 进程退出。

---

## 6. Scene 与 Project 的生命周期关系

| Scene 模式 | 生命周期绑定关系 | 启停方式 |
|---|---|---|
| **`shared`** | **随 Project 一起启动、一起停止** | 自动，不可单独手动启停 |
| **`isolated`** | **依赖 Project 处于运行状态，但可独立启停** | 用户/API 显式控制 |

### 6.1 `shared` Scene

- 是 Project 的"实时视图"，直接引用 Project 全局实例的内存状态。
- `agent-studio run` 加载 Project 时，自动从 `scenes` 表恢复并启动所有 `shared` Scene。
- Project 停止时，所有 `shared` Scene 必须先停止。
- 对 `shared` Scene 调用 `scene.start` 或 `scene.stop` 应返回 JSON-RPC 错误：`{"code": -32003, "message": "shared scenes cannot be started/stopped independently"}`。

### 6.2 `isolated` Scene

- 是独立的仿真上下文，基于 Project 实例快照创建 CoW 副本。
- 启动 `isolated` Scene 的前提条件：对应 Project 必须已被 `ProjectRuntime` 加载。
- `isolated` Scene 的启停不影响 Project 本身。
- 卸载 Project 时，必须先尝试停止所有运行中的 `isolated` Scene。若某 Scene 拒绝停止（受 `force_stop_on_shutdown` 策略控制），则卸载返回 `False` 并中止；若策略为强制停止，则先停止 Scene 再执行卸载。
- `force_stop_on_shutdown` 默认值为 `false`（优先保护正在运行的仿真 Scene，避免误停）。可通过 CLI 参数 `--force-stop-on-shutdown=true|false` 覆盖，未来也可在 `project.yaml` 的 `config` 中声明持久化默认值。

---

## 7. 通信协议：统一 WebSocket + JSON-RPC 2.0

`ProjectRuntime`（`agent-studio run`）对外暴露 WebSocket + JSON-RPC 2.0 接口，Supervisor 和浏览器客户端都可以连接。

### 7.1 连接拓扑

```
浏览器/客户端 ◄────WebSocket────► Supervisor ◄────WebSocket────► agent-studio run (边缘/本地)
                                      │
                                      ├────WebSocket────► agent-studio run (本地子进程)
                                      │
                                      └────本地调用──────► run-inline (调试)
```

### 7.2 控制面方法（Request → Response）

| 方法 | 说明 |
|---|---|
| `project.stop` | 优雅停止当前 Project，触发 checkpoint 后退出进程 |
| `project.checkpoint` | 立即执行一次全量 checkpoint |
| `project.getStatus` | 返回当前 Project 健康状态和实例摘要 |
| `scene.start` | 启动指定 `isolated` Scene |
| `scene.stop` | 停止指定 `isolated` Scene |
| `state.subscribe` | 客户端订阅实时状态流 |
| `state.unsubscribe` | 客户端取消订阅 |

#### 保留错误码

| 错误码 | 含义 |
|---|---|
| `-32001` | Project 已被其他 runtime 锁定 |
| `-32002` | Scene 不存在 |
| `-32003` | 非法的生命周期迁移 |
| `-32004` | Project 未加载 |

### 7.3 数据面通知（Notification / One-way）

| 方法 | 方向 | 说明 |
|---|---|---|
| `notify.heartbeat` | Runtime → Supervisor/Client | 每 5 秒发送，包含 `project_id`、负载、运行状态 |
| `notify.stateChanged` | Runtime → Supervisor/Client | 实例状态变化事件 |
| `notify.eventPublished` | Runtime → Supervisor/Client | EventBus 上的业务事件透传 |
| `notify.error` | Runtime → Supervisor/Client | 异常告警，payload：`{"level": "error", "code": "...", "message": "...", "timestamp": "..."}` |
| `notify.runtimeOnline` | Runtime → Supervisor | 启动时发送，携带 `project_id` 和 `session_id` |
| `notify.runtimeOffline` | Runtime → Supervisor | 停止时发送 |
| `notify.sessionReset` | Supervisor → Client | 当检测到 runtime 重连时，通知客户端重新订阅 |

### 7.4 会话与重连

每次 `agent-studio run` 启动时生成一个 `session_id`（UUID），并在 `notify.runtimeOnline` 中携带。Supervisor 用 `session_id` 区分新旧连接。当同一个 `project_id` 出现新的 `runtimeOnline` 时，Supervisor 必须：
1. 关闭旧的 WebSocket 连接；
2. 用新连接替换 `project_id → WebSocket` 映射；
3. 向所有订阅该 Project 的客户端广播 `notify.sessionReset`。
如果旧 runtime 仍然存活，它会检测到 WebSocket 断开并自行退出。被标记为 dead 的远程 runtime 若重新连回（携带新的 `session_id`），Supervisor 应视其为新注册，直接更新映射并广播 `notify.sessionReset`，无需人工干预。

### 7.5 批量合并

为避免高频 `metric` 更新淹没连接，实现层可对 `notify.stateChanged` 进行 50–100ms 的批量合并。

---

## 8. `agent-studio run` 进程模型

### 8.1 启动顺序

1. **解析 CLI 参数**：读取 `--project-dir`、`--supervisor-ws`（可选）、`--ws-port`（可选）。
2. **获取运行时排他锁**：在 Project 目录下获取 `.lock` 文件锁。若已被占用，立即退出并报错。
3. **加载 Project**：调用 `ProjectRegistry.load_project(project_id)`。
4. **恢复状态**：`StateManager.restore_project()` → 加载实例快照 + 重放事件日志。
5. **自动启动 `shared` Scenes**：遍历 `scenes` 表，启动 `shared` Scene。
6. **启动外部适配器**：RabbitMQ Consumer、Variable Adapter（OPC-UA / MQTT / REST）。
7. **若提供了 `--ws-port`**：启动本地 WebSocket 服务器，暴露 JSON-RPC 接口。
8. **若提供了 `--supervisor-ws`**：建立 WebSocket 连接，发送 `notify.runtimeOnline`。
9. **进入主循环**：处理 RPC 请求、消费消息、发心跳。
10. **WebSocket 断连处理**：若启动时指定了 `--supervisor-ws`，当检测到 WebSocket 意外断开且 15 秒内未能重连成功后，主动执行优雅停止（按 8.2 顺序）并退出进程，确保不会与新的 runtime 实例并发运行同一 Project。

### 8.2 优雅停止顺序

1. 收到 `project.stop` RPC 或 **SIGTERM**。
2. 停止外部适配器。
3. 停止 `isolated` Scenes（受 `force_stop_on_shutdown` 策略控制，默认 `false`，可通过 `--force-stop-on-shutdown=true|false` 覆盖）。若策略为 `false` 且存在拒绝停止的 Scene，优雅停止流程应**中止**：`project.stop` RPC 返回错误码 `-32003`；SIGTERM 处理函数记录日志后正常返回（不退出进程），由调用方决定是否升级为 SIGKILL。
4. 停止 `shared` Scenes。
5. 禁用自动 checkpoint：将 `project_id` 从 `StateManager.loaded_projects` 中移除，并获取 `StateManager` 内部的 per-project 内存锁（防止 auto-checkpoint 线程与显式 checkpoint/unload 竞态；注意这不是 `.lock` 文件锁）。
6. 执行最终 checkpoint：`StateManager.checkpoint_project()`。
7. 卸载 Project：`ProjectRegistry.unload_project(project_id)`。
8. 释放运行时排他锁并删除 `.lock` 文件。
9. 发送 `notify.runtimeOffline`，断开 WebSocket。
10. 进程退出。

### 8.3 `run-inline` 的停止顺序

1. 收到 SIGINT / SIGTERM。
2. 对每个已加载的 Project，反向执行 8.2 的步骤 2-8。
3. 进程退出。

> **注意**：SIGTERM / SIGINT 作用于整个 `run-inline` 进程，会**无差别地停止所有已加载的 Project**；`run-inline` 模式下不存在按 Project 划分的信号级隔离。

---

### 8.4 Project 内部事件驱动与行为执行模型

Project 加载后，其业务逻辑的**核心动力源**是 `EventBus` 上的事件分发。

#### 8.4.1 事件总线与实例订阅

每个 Project 拥有独立的 `EventBus`。当 `InstanceManager.create()` 创建一个 `Instance` 时，会自动解析该实例 `model.behaviors` 中所有 `trigger.type == "event"` 的行为，将实例注册为对应事件类型的订阅者：

```python
bus.register(instance_id, scope, event_type, handler)
```

当外部适配器（OPC-UA / MQTT / REST）或内部逻辑调用 `bus.publish(event_type, payload, source, scope)` 时，EventBus 会把事件路由到所有匹配的实例，触发 `InstanceManager._on_event(instance, event_type, payload, source)`。

#### 8.4.2 行为匹配与条件过滤

`_on_event` 内部遍历实例的 `behaviors`，按以下规则匹配：

1. **`trigger.type` 必须为 `"event"`**（`stateEnter`、`transition` 等触发器由其他生命周期钩子处理，不响应普通事件）。
2. **`trigger.name` 必须与当前 `event_type` 相等**。
3. **若存在 `when` 表达式**，则通过 `SandboxExecutor` 在行为上下文中求值；只有结果为 `True` 时才继续执行。

`when` 表达式示例：`payload.destinationId != null`

#### 8.4.3 行为上下文（Context）

行为执行时的沙箱上下文包含：

| 变量 | 说明 |
|---|---|
| `this` | 当前实例的代理对象，支持属性级读写 |
| `payload` | 当前事件载荷的代理对象 |
| `source` | 事件来源标识 |
| `dispatch(event_type, payload, target=None)` | 向 EventBus 发布新事件的辅助函数 |

为了让 behavior 脚本中的 `this.variables.xxx = value` 能直接写回原始 `Instance`，实现层使用 `_DictProxy` 对 `Instance` 及其内部 dict 字段做包装：属性访问自动映射到 dict 键读写，同时保留 `payload.get('key')`、`__getitem__` 等常用操作。

#### 8.4.4 Action 执行

匹配成功的 behavior，按顺序执行其 `actions` 列表。当前支持两种 action 类型：

| Action 类型 | 说明 |
|---|---|
| `runScript` | 在 `SandboxExecutor` 中执行 Python 脚本，可直接修改 `this.variables`、`this.attributes`、`this.memory` 等 |
| `triggerEvent` | 发布新事件到 EventBus；`payload` 字段支持字符串表达式（如 `this.id`、`this.variables.steelAmount`），会被沙箱求值后发送 |

脚本执行错误会被**静默捕获**（swallow），防止单个实例的行为异常拖垮整个 EventBus 的事件分发。

#### 8.4.5 状态恢复时的事件重放

`StateManager.restore_project()` 在加载实例后，会重放自上次 checkpoint 以来持久化的事件日志到 EventBus。这意味着：

- **事件不仅是实时驱动源**，也是**历史恢复机制**。
- 所有事件驱动的 behavior 在进程重启后可以通过重放恢复正确的业务状态。

---

## 9. Supervisor 进程模型

### 9.1 职责边界

- **不执行任何 Project 业务逻辑**。
- **本地 spawn**：同机部署时，可直接 `subprocess.Popen("agent-studio run ...")` 启动子进程。实现层优先查找 `PATH` 上的 `agent-studio` 可执行文件，以保持 Supervisor 与 runtime 内部模块的解耦；仅在源码未安装时 fallback 到 `python -m src.runtime.cli.main`。
- **反向注册管理**：接收来自边缘/本地 `agent-studio run` 的 WebSocket 连接，维护 `project_id → WebSocket` 映射。
- **请求路由**：把客户端的 `scene.start`、`project.checkpoint` 等请求转发到对应的 runtime。
- **状态聚合**：收集各 runtime 的心跳和通知，广播给订阅的客户端。
- **异常检测**：心跳超时（默认 15 秒）后标记 runtime 为失联。同机子进程可尝试自动重启；远程 runtime 只能告警。

### 9.2 核心限制

| 能力 | 同机子进程 | 远程/边缘 runtime |
|---|---|---|
| 启动 | ✅ `spawn` | ❌ 必须由边缘编排系统启动 |
| 优雅停止 | ✅ `project.stop` RPC | ✅ `project.stop` RPC |
| 强制停止（SIGTERM/KILL） | ✅ 可直接发信号 | ❌ 必须依赖边缘本地系统 |
| 自动重启 | ✅ 可以 | ❌ 只能告警 |

---

## 10. 与现有代码的兼容性

- `ProjectRegistry`、`InstanceManager`、`SceneManager`、`StateManager`、`SQLiteStore` 等核心代码**逻辑直接复用**，仅需在 `ProjectRegistry.load_project()` 和 `unload_project()` 中增加 `.lock` 文件锁的获取与释放逻辑。
- `SandboxExecutor` 继续作为脚本安全层生效；进程级隔离提供额外的故障隔离层。
- 新增模块按职责拆分为四个顶层包：
  - **`src/cli/`**：统一 CLI 入口。`main.py` 负责 argparse 分发，委托给 `src.supervisor.cli` 和 `src.worker.cli`。
  - **`src/worker/`**：运行时进程外壳。包含 `cli/run_command.py`、`cli/run_inline.py`、`server/jsonrpc_ws.py`。负责把 `runtime` 组装成可独立运行的 OS 进程。
  - **`src/runtime/`**：业务核心逻辑。包含 `event_bus.py`、`instance_manager.py`、`project_registry.py`、`state_manager.py`、`scene_manager.py`、`stores/`、`lib/` 等。不依赖任何上层包。
  - **`src/supervisor/`**：管理平面逻辑。包含 `cli.py`、`gateway.py`、`server.py`。内部严禁导入 `worker` 或 `runtime` 的模块，仅通过 `shutil.which("agent-studio")` 调用 CLI 入口。
- `InstanceManager._on_event` 已完成与 `SandboxExecutor` 的接线，支持 `runScript` 和 `triggerEvent` 两种 action；`_DictProxy` 实现了 behavior 脚本中对 `this.variables.xxx` 的属性级读写。

---

## 11. 设计决策记录

### 决策 1：统一 `agent-studio` CLI 入口
- **原因**：消除 `ProjectWorker` 等过度包装的命名。`agent-studio run` 就是运行一个 Project 的诚实表达；`run-inline` 是开发调试的轻量变体；`supervisor` 是纯管理平面。

### 决策 2：生产隔离 = 一个进程一个 Project
- **原因**：现有代码本身支持一个进程内加载多个 Project，但脚本级故障无法被沙箱完全拦截。强制一个进程只跑一个 Project，是获得 OS 级故障隔离的最小代价方式。

### 决策 3：边缘部署 = 反向注册
- **原因**：Supervisor 不能也不应该跨网络 SSH 到边缘服务器。边缘侧由 systemd/Docker 启动 `agent-studio run`，主动连回 Supervisor。这符合云边协同的真实运维模型。

### 决策 4：Supervisor 的远程控制边界止于 WebSocket
- **原因**：跨网络发信号（SIGTERM/KILL）需要侵入式的基础设施（SSH agent、特权网络）。我们明确把这部分交给边缘编排系统，Supervisor 只负责业务级 RPC 和状态聚合。

### 决策 5：`shared` Scene 随 Project 一起启停
- **原因**：`shared` Scene 直接引用 Project 全局实例的内存状态，没有独立的生命周期意义。Project 停止后，shared Scene 自然失效。

### 决策 6：运行时排他锁
- **原因**：多个 `ProjectRuntime` 进程（或同一个 `run-inline` 和另一个 `run`）并发打开同一个 `runtime.db` 会导致数据损坏。文件锁是最简单且跨平台生效的防御手段。

### 决策 7：EventBus 作为业务逻辑的唯一驱动源
- **原因**：实例的 behavior 统一通过 EventBus 事件触发，可以使实时运行、状态恢复（事件重放）、分布式通知使用同一套语义。所有外部数据变化（OPC-UA / MQTT / REST）都转化为事件发布到 EventBus，再由 `_on_event` 驱动 behavior 执行，避免多入口导致的逻辑分叉。

### 决策 8：将 runtime 拆分为 worker（进程外壳）和 runtime（业务核心）
- **原因**：`runtime` 一词身兼两义，导致包内同时存在"进程生命周期/网络协议"和"业务规则/数据模型"两类代码。把进程外壳提升为独立的 `worker` 包，能让"supervisor 管理 worker → worker 加载 runtime → runtime 执行业务逻辑"的依赖链成为显式的单向结构。
- **收益**：语义清晰；`supervisor` 对 `runtime` 内部完全不可见；`worker` 的进程模型可独立演进。

### 决策 9：脚本错误静默捕获
- **原因**：`SandboxExecutor` 执行 behavior 脚本时可能因用户代码错误抛出异常。若将异常向上冒泡，会导致整个 EventBus 的 `publish` 中断，进而影响同 Project 内其他实例的事件处理。静默捕获并忽略脚本错误，是以"隔离故障"换取"系统整体可用性"的务实选择。

### 决策 10：`_DictProxy` 属性代理
- **原因**：Python dataclass 的字段存储在 `__dict__` 中，但 `Instance.variables` 等本身是嵌套 dict。Behavior 脚本习惯写成 `this.variables.steelAmount = 180` 而不是 `this.variables['steelAmount'] = 180`。`_DictProxy` 在不改变 `Instance` 数据结构的前提下，为沙箱上下文提供了属性级读写的自然语法，同时保证写操作穿透回原始 dict。

## 12. 已实现与后续待设计事项

### 已实现
- `agent-studio` CLI 统一入口与参数解析（`run`、`run-inline`、`supervisor`）。
- `src/runtime/locks/project_lock.py` 跨平台文件锁（Windows / Linux），含 Windows 双文件 workaround。
- `src/runtime/server/jsonrpc_ws.py` 通用 JSON-RPC over WebSocket 协议层。
- `src/supervisor/gateway.py` + `server.py` 的 Supervisor HTTP/WebSocket 网关基础实现。
- `shared` Scene 自动恢复、`force_stop_on_shutdown` 策略、15 秒断连自毁等运行时细节。
- `InstanceManager._on_event` 的行为执行（`runScript` / `triggerEvent` / `when` 条件过滤）与 `_DictProxy` 属性代理。

### 后续待设计
- `src/runtime/adapters/` 的适配器基类与数据源配置 schema。
- Supervisor HTTP API 的 OpenAPI schema 设计。
- 客户端 SDK 设计与浏览器端订阅/状态同步协议封装。
