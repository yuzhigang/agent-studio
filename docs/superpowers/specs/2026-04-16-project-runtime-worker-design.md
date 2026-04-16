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
- 对 `shared` Scene 调用 `scene.start` 或 `scene.stop` 应返回 JSON-RPC 错误：`{"code": -32602, "message": "shared scenes cannot be started/stopped independently"}`。

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
| `-32602` | 非法参数（如对 `shared` Scene 调用 `scene.start` / `scene.stop`） |

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

### 8.2 优雅停止顺序

1. 收到 `project.stop` RPC 或 **SIGTERM**。
2. 停止外部适配器。
3. 停止 `isolated` Scenes（受 `force_stop_on_shutdown` 策略控制，默认 `false`，可通过 `--force-stop-on-shutdown=true|false` 覆盖）。
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

## 9. Supervisor 进程模型

### 9.1 职责边界

- **不执行任何 Project 业务逻辑**。
- **本地 spawn**：同机部署时，可直接 `subprocess.Popen("agent-studio run ...")` 启动子进程。
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
- 新增模块主要集中在 CLI 入口、`runtime/locks/`（跨平台文件锁）和 `runtime/adapters/`（外部数据源适配器）。

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

---

## 12. 后续待设计事项

- `agent-studio` CLI 的详细参数解析与入口分发。
- `src/runtime/locks/` 跨平台文件锁实现（Windows / Linux）。
- `src/runtime/adapters/` 的适配器基类与数据源配置 schema。
- Supervisor 的 HTTP/WebSocket 网关接口与客户端 SDK 设计。
- Supervisor HTTP API 的 OpenAPI schema 设计。
