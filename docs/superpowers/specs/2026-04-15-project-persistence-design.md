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

- `project.yaml`：静态源文件，包含 `project_id`、`name`、`description`、`config` 等全局配置。`ProjectRegistry` 加载时从 `project.yaml` 读取，并镜像写入 `runtime.db` 的 `projects` 表作为运行时缓存。
- `runtime.db`：统一存储 `scenes`（运行时状态）、`instances`、`event_log`、`project_state`。
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
    def list_instances(self, project_id: str, scope: str | None = None, lifecycle_state: str | None = None) -> list[dict]: ...
    def delete_instance(self, project_id: str, instance_id: str, scope: str) -> bool: ...

class EventLogStore(ABC):
    def append(self, project_id: str, event_id: str, event_type: str, payload: dict, source: str, scope: str) -> None: ...
    def replay_after(self, project_id: str, last_event_id: str | None) -> list[dict]: ...
    """返回按 timestamp ASC 排序的事件列表。若 last_event_id 为 None，则返回全部事件。
    若 last_event_id 不为 None 但在 event_log 中不存在，抛出 ValueError 以提示数据不一致。""""
```

### 4.2 SQLiteStore 实现

- **按 Project 实例化**：`SQLiteStore(project_dir)` 只操作该目录下的 `runtime.db`。
- **单连接 + `threading.Lock()`**：同一个 Project 内的并发写入由 Python 锁保护。
- **WAL 模式**：开启 `PRAGMA journal_mode=WAL`，保证读操作不被写阻塞。
- **外键约束**：`PRAGMA foreign_keys = ON;` 已开启，但当前 schema 暂不明确声明 `FOREIGN KEY`（SQLite 允许无外键声明运行，后续需要强一致性时可追加）。
- **UPSERT 语义**：`save_instance` 和 `save_scene` 采用 SQLite `ON CONFLICT DO UPDATE`（SQLite 3.24+ 支持，Python 3.11+ 自带版本已满足），保证幂等覆盖且不会丢失未参与 INSERT 的列（如未来可能增加的 `created_at`）。
- **snapshot 字段映射**：`save_instance` 接收的 `snapshot: dict` 必须包含与 schema 对应的键：`model_name`（必选）、`model_version`（可选，可为 `None`）、`attributes`、`state`、`variables`、`links`、`memory`、`audit`、`lifecycle_state`、`updated_at`。`SQLiteStore` 负责将 JSON 字段序列化后写入对应列；`model_version` 为 `None` 时写入 SQL NULL。
- **Model 对象不持久化**：完整的 `Instance.model` dict 不序列化到 DB；仅保存 `model_name` 和 `model_version`，恢复时通过 `ModelLoader` 重新加载完整 `model`。

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
    refs TEXT NOT NULL,
    local_instances TEXT NOT NULL,
    last_event_id TEXT,
    checkpointed_at TEXT,
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
    attributes TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS project_state (
    project_id TEXT PRIMARY KEY,
    last_event_id TEXT,
    checkpointed_at TEXT NOT NULL
);
```

### 4.4 EventBus 事件持久化机制

`EventBus.publish()` 本身不直接写 `event_log`，以避免 I/O 阻塞高频消息。事件持久化通过显式包装完成：

```python
class PersistentEventBus:
    def __init__(self, bus: EventBus, event_log_store: EventLogStore):
        self._bus = bus
        self._store = event_log_store

    def publish(self, event_type, payload, source, scope, target=None, *, persist=True):
        self._bus.publish(event_type, payload, source, scope, target)
        if persist:
            self._store.append(
                project_id=..., event_id=generate_uuid(),
                event_type=event_type, payload=payload,
                source=source, scope=scope,
            )
```

- 默认 `persist=True`，关键业务事件（状态迁移、外部指令）直接落盘。
- 高频遥测或内部心跳事件可显式传 `persist=False` 跳过写入。
- `StateManager.checkpoint_project()` 在写入实例快照前，先确保最近一批事件已落盘。

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
- `load_project()` 初始化 `SQLiteStore`（同时作为 Project/Scene/Instance/EventLog Store）、`EventBusRegistry`（已存在于 `src/runtime/event_bus.py`，负责按 `project_id` 创建/销毁 `EventBus`）、`InstanceManager`、`SceneManager`、`StateManager`，返回运行时 bundle。
- `unload_project()` 关闭 SQLite 连接、清空内存实例、释放 EventBus。

## 6. StateManager

```python
class StateManager:
    def __init__(
        self,
        instance_manager: InstanceManager,
        scene_manager: SceneManager,
        instance_store: InstanceStore,
        scene_store: SceneStore,
        event_log_store: EventLogStore,
        metric_store: MetricStore | None = None,
    ): ...
    def checkpoint_project(self, project_id: str, last_event_id: str | None = None) -> None: ...
    def restore_project(self, project_id: str) -> bool: ...
    def checkpoint_scene(self, project_id: str, scene_id: str) -> None: ...
    def restore_scene(self, project_id: str, scene_id: str) -> dict | None: ...
    def shutdown(self) -> None: ...
```

### 6.1 Checkpoint

- 遍历该 Project 下所有 `active` 和 `completed` 实例。
- 在一个 SQLite 事务中原子写入：实例快照 + `lastEventId` 到 `project_state` 表。
- `project_state` 表以 `project_id` 为唯一主键，**仅保留最新的 checkpoint 元数据**，不保留历史版本。
- 若事务失败（如磁盘满、DB 锁定），`checkpoint_project()` 抛出 `RuntimeError`（或自定义 `PersistenceError`），且内存状态保持不变。
- 显式 checkpoint 由业务层在关键状态迁移后调用；同时 `StateManager` 内部维护一个 `loaded_projects: set[str]`（受 `threading.Lock()` 保护），并启动一个轻量后台线程，每 30 秒对该集合的快照执行自动 checkpoint。
- 后台线程在对某个 Project 执行 checkpoint 前，先尝试获取该 Project 的 per-project 锁；若获取失败（说明正在 unload），则跳过。
- `unload_project()` 必须在释放资源前先将 `project_id` 从 `loaded_projects` 中移除，再调用 `StateManager.shutdown()` 优雅停止后台线程，防止对正在卸载的 Project 执行 auto-checkpoint。
- `MetricStore` 由 `ProjectRegistry.load_project()` 在构造 `StateManager(metric_store=...)` 时注入，用于 metric 回填。`load_project()` 的伪代码如下：
  ```python
  store = SQLiteStore(project_dir)
  bus_reg = EventBusRegistry()
  im = InstanceManager(bus_reg, instance_store=store)
  metric_store = metric_store_factory(project_id) if metric_store_factory else None
  state_mgr = StateManager(im, scene_mgr, store, store, store, metric_store=metric_store)
  scene_mgr = SceneManager(im, bus_reg, scene_store=store, state_manager=state_mgr)
  ```

### 6.3 Scene Checkpoint 语义

- `checkpoint_scene(project_id, scene_id)`：原子快照所有 `scope == f"scene:{scene_id}"` 的实例（包括 CoW 副本和 local instances），同时保存 scene 自身的运行时状态到 `scenes` 表。
- `restore_scene(project_id, scene_id)`：从 DB 加载 scene 运行时状态和关联实例，重新注册到 EventBus，并执行 metric 回填与 Property Reconciliation。

### 6.2 Restore

1. 从 `InstanceStore` 读取 `active` / `completed` 实例快照到内存（`archived` 实例按需懒加载）。
2. 从 `project_state` 表读取 `lastEventId`。
3. 从 `EventLogStore` 重放后续事件（幂等处理）。
4. 对 `metric` 变量执行时序库回填（如果 `MetricStore` 可用）。
5. 执行 Property Reconciliation。

## 7. InstanceManager 改造

- 构造函数注入可选的 `instance_store`。
- `create()` / `copy_for_scene()` 在内存操作成功后自动同步到 `instance_store`（同步的字段包括 `attributes`、`state`、`variables`、`links`、`memory`、`audit` 等完整快照；空 `attributes` 序列化为 `{}`）。
- `remove()` 从内存中删除实例，并调用 `instance_store.delete_instance()` 物理删除 DB 记录。生命周期中的 `purged` 状态由 `transition_lifecycle()` 显式设置并写入 tombstone 快照后，再由调用方决定是否调用 `remove()` 物理删除。
- 新增 `transition_lifecycle(project_id, instance_id, new_state)`：
  - 更新内存中的 `lifecycle_state`。
  - 同步写入 DB（写入完整快照，非 tombstone）。
  - 若新状态为 `archived`，立即从内存中卸载。
- `get()` 增加懒加载机制：当内存中未命中且配置了 `instance_store` 时，尝试从 DB 读取快照并重新水合为 `Instance` 对象（`model` 字段通过 `ModelLoader` 重新加载）。

## 8. SceneController → SceneManager

- 类名和文件名统一改为 `SceneManager`。
- 构造函数注入可选的 `scene_store` 和 `state_manager`。
- `start()` 成功后调用 `scene_store.save_scene()`，持久化的是**运行时 Scene 状态**（`mode`、`refs`、`local_instances` 等）；静态 Scene 定义模板仍保留在 `scenes/` 目录下的 YAML 文件中。
- `scenes` 表中存在一行即代表该 Scene 在最后一次保存时处于运行状态，schema 中不设额外的 `status` 列。
- `stop()` 执行顺序：(1) 停止并移除 scene 内所有 local / CoW 实例；(2) 调用 `scene_store.delete_scene()` 删除运行时状态；(3) 仅当 (1)(2) 均成功时返回 `True`。静态 Scene 定义不受此操作影响。
- 新增 `list_by_project(project_id)` 查询该 Project 下所有运行时 Scene 状态。

## 9. MetricStore

保留现有 stub 语义，新增正式基类：

```python
from typing import Any

class MetricStore(ABC):
    def write(self, project_id: str, instance_id: str, variable: str, value, timestamp: datetime) -> None: ...
    def latest(self, project_id: str, instance_id: str, variable: str) -> Any | None: ...
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
