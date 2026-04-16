# 源码包结构重塑设计：supervisor / worker / runtime / cli

## 1. 背景与问题

当前 `src/runtime/` 包同时承载了两层截然不同的职责：

1. **业务核心层**：`EventBus`、`InstanceManager`、`ProjectRegistry`、`StateManager`、`SceneManager`、`stores`、`lib/sandbox.py` 等。这部分是纯业务逻辑，不感知"进程"或"网络"。
2. **进程/服务层**：`cli/main.py`、`run_command.py`、`run_inline.py`、`locks/project_lock.py`、`server/jsonrpc_ws.py`。这部分负责把业务核心包装成一个可运行的 OS 进程，处理 CLI、文件锁、WebSocket 协议。

这导致两个问题：
- **语义模糊**：`runtime` 一词既指"业务内核"，又指"运行时进程"，新人难以快速定位代码。
- **依赖边界不显著**：虽然 `supervisor` 已在代码层面与 `runtime` 解耦，但 `runtime` 包内部"业务核"与"进程壳"混在一起，无法通过包结构显式约束"进程壳只能调用业务核公开 API"。

## 2. 目标

将 `src/runtime/` 中的"进程/服务层"拆出，形成清晰的三层包结构：

- **`src/cli/`**：统一 CLI 入口，只做 argparse 分发。
- **`src/supervisor/`**：管理平面（HTTP/WebSocket 网关、进程映射）。已独立，保持不变。
- **`src/worker/`**：运行时**进程外壳**。负责把 `runtime` 组装成一个可独立运行的 OS 进程（CLI 子命令实现、文件锁、WebSocket 服务器）。
- **`src/runtime/`**：业务**核心逻辑**。负责 Project 加载后内部的全部业务规则（EventBus、InstanceManager、State/Scene Manager、stores 等）。

## 3. 文件迁移映射

### 3.1 新增/移动（进程/服务层迁出 runtime）

| 操作 | 源路径 | 目标路径 |
|---|---|---|
| 移动 | `src/runtime/cli/main.py` | `src/cli/main.py` |
| 移动 | `src/runtime/cli/__init__.py` | `src/worker/cli/__init__.py` |
| 移动 | `src/runtime/cli/run_command.py` | `src/worker/cli/run_command.py` |
| 移动 | `src/runtime/cli/run_inline.py` | `src/worker/cli/run_inline.py` |
| 移动 | `src/runtime/locks/__init__.py` | `src/worker/locks/__init__.py` |
| 移动 | `src/runtime/locks/project_lock.py` | `src/worker/locks/project_lock.py` |
| 移动 | `src/runtime/server/__init__.py` | `src/worker/server/__init__.py` |
| 移动 | `src/runtime/server/jsonrpc_ws.py` | `src/worker/server/jsonrpc_ws.py` |

### 3.2 保留在 `src/runtime/`（业务核心）

- `src/runtime/__init__.py`
- `src/runtime/event_bus.py`
- `src/runtime/instance.py`
- `src/runtime/instance_manager.py`
- `src/runtime/project_registry.py`
- `src/runtime/state_manager.py`
- `src/runtime/scene_manager.py`
- `src/runtime/scene_controller.py`
- `src/runtime/metric_store.py`
- `src/runtime/model_loader.py`
- `src/runtime/persistent_event_bus.py`
- `src/runtime/lib/**`
- `src/runtime/stores/**`

### 3.3 测试文件迁移

| 操作 | 源路径 | 目标路径 |
|---|---|---|
| 移动 | `tests/runtime/cli/` | `tests/worker/cli/` |
| 移动 | `tests/runtime/locks/` | `tests/worker/locks/` |
| 移动 | `tests/runtime/server/` | `tests/worker/server/` |
| 移动 | `tests/runtime/test_e2e_local_spawn.py` | `tests/worker/test_e2e_local_spawn.py` |
| 保留 | `tests/supervisor/` | 不变 |
| 保留 | `tests/runtime/test_*.py`（业务核心测试） | 不变 |

### 3.4 根目录保留

- `projects/`：运行时数据目录，保留在根目录（建议加入 `.gitignore`）。
- `agents/`：Agent 模型定义库（内容资产），保留在根目录。

## 4. 关键 Import 变更

### `src/cli/main.py`
```python
# 旧
from src.runtime.cli.run_command import run_main
from src.runtime.cli.run_inline import run_inline_main
from src.runtime.cli.supervisor_command import supervisor_main

# 新
from src.worker.cli.run_command import run_main
from src.worker.cli.run_inline import run_inline_main
from src.supervisor.cli import supervisor_main
```

### `src/worker/cli/run_command.py` / `run_inline.py`
```python
# 旧
from src.runtime.project_registry import ProjectRegistry
from src.runtime.state_manager import StateManager
from src.runtime.server.jsonrpc_ws import JsonRpcWebSocketServer

# 新
from src.runtime.project_registry import ProjectRegistry
from src.runtime.state_manager import StateManager
from src.worker.server.jsonrpc_ws import JsonRpcWebSocketServer
```

### `src/supervisor/server.py`
保持不变。依然通过 `shutil.which("agent-studio")` 调用 CLI 入口，**严禁**直接导入 `worker` 或 `runtime` 内部模块。

## 5. 依赖边界规则

调整后的包间依赖必须满足以下规则：

```
src/cli ──► src/supervisor/cli
src/cli ──► src/worker/cli
src/worker ──► src/runtime
src/supervisor ──╳ 不依赖 worker/runtime 内部
src/runtime ──╳ 不依赖任何人
```

1. **`src/cli` → `src/supervisor` / `src/worker`**：只做 argparse 解析和子命令分发。
2. **`src/worker` → `src/runtime`**：`worker` 可以导入 `runtime` 的全部内部模块，职责是"把它们组装成一个可运行的 OS 进程"。
3. **`src/supervisor` ╳ `src/worker` / `src/runtime`**：内部严禁导入 `worker` 或 `runtime` 的模块，唯一依赖是 CLI 可执行文件名。
4. **`src/runtime` ╳ 任何人**：业务核心不依赖上层包。

## 6. 对现有 spec 的影响

需同步更新 `docs/superpowers/specs/2026-04-16-project-runtime-worker-design.md`：

- 第 10 节 "与现有代码的兼容性"：将包结构描述从 `src/runtime/` + `src/supervisor/` 更新为 `src/cli/` + `src/worker/` + `src/runtime/` + `src/supervisor/`。
- 新增一条设计决策记录：解释为什么要从 `runtime` 中拆出 `worker` 层。

> **时序建议**：先完成本 spec 指导的代码迁移与测试验证，在所有 import 路径和测试通过后再一次性回写 `2026-04-16-project-runtime-worker-design.md`，避免两份文档频繁交叉修改导致不一致。

## 7. 新增设计决策

### 决策：将 runtime 拆分为 worker（进程外壳）和 runtime（业务核心）

- **原因**：`runtime` 一词身兼两义，导致包内同时存在"进程生命周期/网络协议"和"业务规则/数据模型"两类代码。把进程外壳提升为独立的 `worker` 包，能让"supervisor 管理 worker → worker 加载 runtime → runtime 执行业务逻辑"的依赖链成为显式的单向结构。
- **收益**：
  - 语义清晰：`worker` 是 OS 进程，`runtime` 是业务内核。
  - 边界强制：`supervisor` 对 `runtime` 内部完全不可见，只能看到 CLI 入口。
  - 可替换性：未来 worker 的进程模型（线程池、容器、Wasm）可以独立演进，不影响 runtime 业务逻辑。
