# Project-Instance-Scene 持久化架构设计文档

## 1. 背景与目标

当前 `Project-Instance-Scene` 运行时架构（`EventBus`、`InstanceManager`、`SceneController`）完全基于内存运行。随着业务需求演进，Project、Scene 和 Instance 都需要被持久化，支持：

- 进程重启后的状态恢复。
- 实例生命周期管理（`active → completed → archived → purged`）。
- `metric` 与 `state` 类变量的差异化存储策略落地。

## 2. 核心设计原则

1. **Project 自包含**：每个 Project 拥有独立的文件夹和 `runtime.db`，可整体迁移、备份、归档。
2. **零新增外部依赖**：默认使用 Python 内置 `sqlite3`，无需额外安装数据库。
3. **并发隔离**：不同 Project 的 DB 文件完全隔离，彻底消除跨 Project 锁竞争。
4. **Checkpoint + Event Log 双轨恢复**：实例快照 + 事件日志重放，保证 at-least-once 恢复语义。

## 3. Project 文件夹结构

```yaml
projects/
└── steel-plant-01/              # project_id
    ├── project.yaml             # Project 元数据、全局配置
    ├── runtime.db               # SQLite 运行时数据库
    ├── scenes/                  # Scene 静态定义/模板（可选）
    └── resources/               # 外部资源、导入文件、附件
```

- `project.yaml`：包含 `project_id`、`name`、`description`、`config` 等全局配置。
- `runtime.db`：统一存储 `scenes`、`instances`、`event_log`。
- 整个文件夹可复制到任意环境直接加载运行。

## 4. Store 抽象层

### 4.1 接口定义

```python
class ProjectStore(ABC):
    def save_project(self, project_id: str, config: dict) -> None: ...
    def load_project(self, project_id: str) -> dict | None: ...
    def delete_project(self, project_id: str) -> bool: ...

class SceneStore(ABC):
    def save_scene(self, project_id: str, scene_id: str, scene_data: dict) -> None: ...
    def load_scene(self, project_id: str, scene_id: str) -> dict | None: ...
    def list_scenes(self, project_id: str) -> list[dict]: ...
    def delete_scene(self, project_id: str, scene_id: str) -> bool: ...

class InstanceStore(ABC):
    def save_instance(self, project_id: str, instance_id: str, scope: str, snapshot: dict) -> None: ...
    def load_instance(self, project_id: str, instance_id: str, scope: str) -> dict | None: ...
    def list_instances(self, project_id: str, scope: str | None = None) -> list[dict]: ...
    def delete_instance(self, project_id: str, instance_id: str, scope: str) -> bool: ...

class EventLogStore(ABC):
    def append(self, project_id: str, event_id: str, event_type: str, payload: dict, source: str, scope: str) -> None: ...
    def replay_after(self, project_id: str, last_event_id: str) -> list[dict]: ...
```

### 4.2 SQLiteStore 实现

- **按 Project 实例化**：`SQLiteStore(project_dir)` 只操作该目录下的 `runtime.db`。
- **单连接 + `threading.Lock()`**：同一个 Project 内的并发写入由 Python 锁保护。
- **WAL 模式**：开启 `PRAGMA journal_mode=WAL`，保证读操作不被写阻塞。

### 4.3 表结构

```sql
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    config TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    project_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    references TEXT NOT NULL,
    local_instances TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, scene_id)
);

CREATE TABLE IF NOT EXISTS instances (
    project_id TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    state TEXT NOT NULL,
    variables TEXT NOT NULL,
    links TEXT NOT NULL,
    memory TEXT NOT NULL,
    audit TEXT NOT NULL,
    lifecycle_state TEXT DEFAULT 'active',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, instance_id, scope)
);

CREATE TABLE IF NOT EXISTS event_log (
    project_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    PRIMARY KEY (project_id, event_id)
);
```

## 5. ProjectRegistry

`ProjectRegistry` 是全局入口，负责发现、加载、卸载 Project：

```python
class ProjectRegistry:
    def __init__(self, base_dir: str = "projects"): ...
    def create_project(self, project_id: str, config: dict | None = None) -> dict: ...
    def load_project(self, project_id: str) -> dict: ...
    def unload_project(self, project_id: str) -> bool: ...
    def list_projects(self) -> list[str]: ...
```

- `create_project()` 创建文件夹、`project.yaml`、`runtime.db`。
- `load_project()` 初始化 `SQLiteStore`、`EventBusRegistry`、`InstanceManager`、`SceneManager`、`StateManager`，返回运行时 bundle。
- `unload_project()` 关闭 SQLite 连接、清空内存实例、释放 EventBus。

## 6. StateManager

```python
class StateManager:
    def checkpoint_project(self, project_id: str, last_event_id: str | None = None) -> None: ...
    def restore_project(self, project_id: str) -> bool: ...
    def checkpoint_scene(self, project_id: str, scene_id: str) -> None: ...
    def restore_scene(self, project_id: str, scene_id: str) -> dict | None: ...
```

### 6.1 Checkpoint

- 遍历该 Project 下所有 `active` 和 `completed` 实例。
- 在一个 SQLite 事务中原子写入：实例快照 + `lastEventId`。
- 显式 checkpoint 由业务层在关键状态迁移后调用；同时 `StateManager` 内部启动一个轻量后台线程，每 30 秒自动 checkpoint 所有已加载的 Project。

### 6.2 Restore

1. 从 `InstanceStore` 读取实例快照到内存。
2. 读取 `lastEventId`。
3. 从 `EventLogStore` 重放后续事件（幂等处理）。
4. 对 `metric` 变量执行时序库回填（如果 `MetricStore` 可用）。
5. 执行 Property Reconciliation。

## 7. InstanceManager 改造

- 构造函数注入可选的 `instance_store`。
- `create()` / `remove()` / `copy_for_scene()` 在内存操作成功后自动同步到 `instance_store`。
- 新增 `transition_lifecycle(project_id, instance_id, new_state)`：
  - 更新内存中的 `lifecycle_state`。
  - 同步写入 DB。
  - 若新状态为 `archived`，立即从内存中卸载（下次需要时从 DB 懒加载）。

## 8. SceneController → SceneManager

- 类名和文件名统一改为 `SceneManager`。
- 构造函数注入可选的 `scene_store` 和 `state_manager`。
- `start()` 成功后调用 `scene_store.save_scene()`。
- `stop()` 成功后调用 `scene_store.delete_scene()`。
- 新增 `list_by_project(project_id)` 查询该 Project 下所有 Scene。

## 9. MetricStore

保留现有 stub 语义，新增正式基类：

```python
class MetricStore(ABC):
    def write(self, project_id: str, instance_id: str, variable: str, value, timestamp: datetime) -> None: ...
    def latest(self, project_id: str, instance_id: str, variable: str): ...
```

同时提供 `MemoryMetricStore` 用于测试环境。

## 10. 并发与事务策略

- **Project 之间**：完全并行，零锁竞争（每个 Project 独立 `.db` 文件）。
- **Project 内部**：`SQLiteStore` 单连接 + `threading.Lock()` 保护写入，WAL 模式保证读写不阻塞。
- **内存运行时**：保留现有的 `InstanceManager._lock` + `EventBus._lock` 机制。

## 11. 测试策略

1. `tests/runtime/stores/test_sqlite_store.py`：Store CRUD 单元测试。
2. `tests/runtime/test_project_registry.py`：ProjectRegistry 完整生命周期测试。
3. `tests/runtime/test_state_manager.py`：checkpoint → 内存清空 → restore 一致性验证。
4. 更新现有测试：适配 `SceneManager` 重命名和新增持久化行为。
