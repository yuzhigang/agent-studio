# LibContext + Dataset 数据访问设计

**日期**: 2026-04-20
**状态**: 定稿

## 背景

Agent Studio 中，除了 `ladle`（钢包）、`crane`（天车）这类**有行为、有状态机**的智能体外，还存在大量业务数据实体（板坯、生产订单、钢卷等）。这些实体：

- 数量巨大（万级+），不适合作为独立 `Instance` 入内存管理
- 有明确业务字段结构，需要条件查询
- 数据可能来自外部系统（MES、ERP）或 SQLite 存储
- 需要被 Agent 查询、引用和传递

本设计在**零新增系统级抽象**的前提下，让 Agent 通过 lib 读写外部数据，同时保证数据源类型变化时业务逻辑无需修改。

## 核心原则

1. **零新概念**：没有 `Swarm`、`entity_type` 等专属概念。slab_manager 就是普通 Agent Model，slab 就是普通 Model。
2. **复用现有机制**：`@lib_function`、`LibProxy`、`binding` 全部是已有概念，只增加运行时注入逻辑。
3. **数据源与业务解耦**：Dataset 统一封装数据源访问，binding 类型变化时 lib 逻辑不变。
4. **Context 自动注入**：Lib 函数通过 `self._context` 访问运行时信息（this、payload、dispatch 等），无需额外参数。

## 核心概念

### 术语表

| 术语 | 定义 |
|------|------|
| **LibContext** | 运行时注入 lib 实例的上下文，含 `this`、`payload`、`source`、`dispatch`、`world_state` |
| **Dataset** | 系统级工具类，统一封装不同数据源类型的访问逻辑（SQLite、API 等） |

## 架构设计

### 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│  behavior script（业务层）                                     │
│  slabs = lib.dao.getSlabs({"status": "produced"}, limit=100)  │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  lib / dao.py（用户层，@lib_function 标记）                    │
│  class SlabDao:                                              │
│      @lib_function(name="getSlabs")│
│      def get_slabs(self, args):                              │
│          cfg = self._context["this"].bindings.slabs          │
│          ds = Dataset(cfg)                                   │
│          return ds.query(args.get("filters"), limit=50)      │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  系统层                                                        │
│  ├── Dataset（统一数据源封装）                                 │
│  │   ├── SQLiteAdapter（连接池、参数化查询）                   │
│  │   ├── HttpAdapter（HTTP 请求、响应解析）                    │
│  │   └── 未来可扩展：mysql、redis...                           │
│  ├── LibProxy（lib 调用代理 + LibContext 注入）                │
│  └── SandboxExecutor（沙箱执行 + 预加载模块）                  │
└──────────────────────────────────────────────────────────────┘
```

### 关键特性

| 特性 | 说明 |
|------|------|
| `@lib_function` 签名不变 | 不增加任何参数 |
| `lib.dao` 自动补全 namespace | `default_namespace=instance.model_name`，`lib.dao` = `lib.slab_manager.dao` |
| binding 自取 | Lib 通过 `self._context["this"].bindings.slabs` 自取配置，无需显式传入 |
| 数据源类型透明 | `Dataset(cfg)` 自动根据 `cfg.type` 选择 Adapter，lib 逻辑不变 |

## LibContext 机制

### 注入时机

`LibProxy` 在调用 lib 函数前，将 `LibContext` 注入到 bound method 所属实例的 `_context` 属性：

```python
# src/runtime/lib/proxy.py
class _LibProxyNode:
    def __call__(self, *args, **kwargs):
        func = self._resolve_func()

        # 注入 LibContext 到 lib class 实例
        instance = getattr(func, '__self__', None)
        if instance and self._lib_context is not None:
            instance._context = self._lib_context

        return func(*args, **kwargs)
```

### LibContext 结构

```python
lib_context = {
    "this":         _wrap_instance(instance),      # 含 bindings、variables、attributes 等
    "payload":      _DictProxy(payload),           # 当前事件 payload
    "source":       source,                        # 事件来源
    "dispatch":     dispatch,                      # 事件分发函数
    "world_state":  _DictProxy(world_state),       # 世界状态快照
}
```

### 使用方式

```python
# lib 内部访问
class SlabDao:
    @lib_function(name="getSlabs")
    def get_slabs(self, args):
        this = self._context["this"]
        cfg = this.bindings.slabs          # 自取 binding 配置
        ds = Dataset(cfg)
        return ds.query(args.get("filters", {}), args.get("limit", 50))

    @lib_function(name="notifySlabChanged")
    def notify_slab_changed(self, args):
        # 也可以 dispatch 事件
        dispatch = self._context["dispatch"]
        dispatch("slab.changed", {
            "slabId": args.get("slabId"),
            "status": args.get("status")
        })
```

## Dataset 工具类

### 设计定位

Dataset 是**系统级独立组件**，不属于 lib，也不属于 shared lib。它是一个运行时工具类，由 lib 或 behavior script 按需调用。

```
Dataset（系统级工具类）
├── 输入：binding 配置（type, connection, table, fieldMap...）
├── 内部：根据 type 自动选择 Adapter
│   ├── sqlite → SQLiteAdapter
│   ├── api    → HttpAdapter
│   └── 未来可扩展...
└── 输出：统一的数据操作方法
```

### 预加载注入

Dataset 作为系统普通模块存在，lib 文件直接导入：

```python
# agents/roles/slab_manager/libs/dao.py
from src.runtime.lib.dataset import Dataset
```

lib 文件在系统环境中加载（不在沙箱内），可直接 import 系统模块。behavior script 如需使用 Dataset，通过 lib 间接调用。

### API 设计

```python
class Dataset:
    def __init__(self, cfg: dict):
        """
        cfg 来自 this.bindings.xxx，结构：
        {
            "type": "sqlite" | "api",
            "connection": "./runtime.db" | "http://mes/api/slabs",
            "table": "slabs",
            "primaryKey": "id",
            "fieldMap": {"id": "id", "grade": "grade", ...}
        }
        """
        self._adapter = _create_adapter(cfg["type"], cfg)

    def query(self, filters: dict, limit: int = 50, offset: int = 0) -> list[dict]:
        """条件查询，返回 Model 字段格式的记录列表"""
        ...

    def get(self, id: str) -> dict | None:
        """按主键获取单条记录"""
        ...

    def create(self, data: dict) -> dict:
        """创建记录，返回创建后的记录"""
        ...

    def update(self, id: str, data: dict) -> dict:
        """更新记录，返回更新后的记录"""
        ...

    def delete(self, id: str) -> bool:
        """删除记录"""
        ...

    def count(self, filters: dict | None = None) -> int:
        """条件计数"""
        ...
```

### fieldMap 自动处理

Dataset 内部自动处理 fieldMap 的正向/反向映射：

```python
# 写入：Model 字段 → 外部字段
# 用户传入 {"grade": "Q235B", "width": 1200}
# Dataset 自动映射为 {"steel_grade": "Q235B", "w": 1200}（根据 fieldMap）

# 读取：外部字段 → Model 字段
# 外部返回 {"slab_no": "S001", "steel_grade": "Q235B"}
# Dataset 自动映射为 {"id": "S001", "grade": "Q235B"}
```

## 变量与 Binding 同名对应

```yaml
# agents/roles/slab_manager/model/index.yaml
variables:
  slabs:
    type: object
    ref: slab           # 引用 slab model
    default: {}

# worlds/.../slm-01.instance.yaml
variables:
  slabs: {}              # 运行时缓存查询结果

bindings:
  slabs:                 # binding key 与变量名相同，前后对应
    type: sqlite
    connection: ./runtime.db
    table: slabs
    primaryKey: id
    fieldMap:
      id: id
      grade: grade
      width: width
```

## 完整示例

### slab Model

```yaml
# agents/logistics/slab/model/index.yaml
$schema: https://agent-studio.io/schema/v2
metadata:
  name: slab
  title: 板坯
  group: logistics

attributes:
  grade: { type: string, title: 钢种 }
  width: { type: number, title: 宽度, x-unit: mm }
  thickness: { type: number, title: 厚度, x-unit: mm }
  length: { type: number, title: 长度, x-unit: mm }

variables:
  temperature: { type: number, x-unit: "℃", x-category: metric }
  location: { type: string }
  status: { type: string, default: "produced", enum: [produced, cooled, inspected, shipped] }
  weight: { type: number, x-unit: kg }
```

### slab_manager Model

```yaml
# agents/roles/slab_manager/model/index.yaml
metadata:
  name: slab_manager
  title: 板坯管理员
  group: roles

attributes:
  syncIntervalSec:
    type: number
    default: 30

variables:
  lastSyncTime: { type: string, default: "" }
  slabs: { type: object, ref: slab, default: {} }

behaviors:
  - name: onSlabStatusChanged
    trigger:
      type: event
      name: external.slabStatusUpdate
    actions:
      - type: runScript
        script: |
          slab = lib.dao.getSlab({"slabId": payload.slabId})
          lib.dao.updateSlab({
              "slabId": payload.slabId,
              "data": {"status": payload.status}
          })
          dispatch("slab.statusChanged", {
              "slabId": payload.slabId,
              "fromStatus": slab.status,
              "toStatus": payload.status
          })

services:
  getSlab:
    description: 获取单个板坯详情
    input:
      slabId: { type: string }
    output:
      slab: { type: object }

  querySlabs:
    description: 查询板坯列表
    input:
      filters: { type: object }
      limit: { type: number, default: 50 }
    output:
      items: { type: array }
      total: { type: number }
```

### slab_manager lib (dao.py)

```python
# agents/roles/slab_manager/libs/dao.py
from src.runtime.lib.decorator import lib_function
from dataset import Dataset


class SlabDao:
    # namespace 省略时，自动从文件路径推断为 slab_manager
    # 建议显式指定简洁缩写，如 namespace="dao"
    @lib_function(name="getSlabs")
    def get_slabs(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.query(args.get("filters", {}), args.get("limit", 50))

    @lib_function(name="getSlab")
    def get_slab(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.get(args.get("slabId"))

    @lib_function(name="updateSlab")
    def update_slab(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.update(args.get("slabId"), args.get("data"))

    @lib_function(name="createSlab")
    def create_slab(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.create(args.get("data"))

    @lib_function(name="deleteSlab")
    def delete_slab(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.delete(args.get("slabId"))

    @lib_function(name="countSlabs")
    def count_slabs(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.count(args.get("filters"))
```

### slab_manager 实例声明

```yaml
# worlds/steel-plant-01/agents/roles/slab_manager/instances/slm-01.instance.yaml
id: slm-01
modelId: slab_manager

state: idle

metadata:
  name: 板坯管理员-01

attributes:
  syncIntervalSec: 30

variables:
  lastSyncTime: ""
  slabs: {}

bindings:
  slabs:
    type: sqlite
    connection: ./runtime.db
    table: slabs
    primaryKey: id
    fieldMap:
      id: id
      grade: grade
      width: width
      thickness: thickness
      temperature: temperature
      location: location
      status: status
```

## 目录结构

```
agents/
  logistics/
    slab/
      model/
        index.yaml              # slab Model 定义
  roles/
    slab_manager/
      model/
        index.yaml              # slab_manager Model：有 behaviors、services
        behaviors.yaml
      instances/
        slm-01.instance.yaml    # 实例声明：含 bindings
      libs/
        dao.py                  # @lib_function 标记的业务 lib
```

## 实施要点

1. **Instance dataclass 扩展**：增加 `bindings: dict` 字段。
2. **`_wrap_instance` 扩展**：暴露 `bindings` 属性到 `this` 命名空间。
3. **`LibProxy` 扩展**：
   - 构造函数增加 `lib_context` 参数
   - `__call__` 中检查 bound method 的实例，注入 `_context`
4. **`InstanceManager._build_behavior_context` 扩展**：
   - 创建 `LibProxy` 时传入 `lib_context`
   - `lib_context` 含 `this`、`payload`、`source`、`dispatch`、`world_state`
   - 将 `lib`（LibProxy 实例）注入沙箱上下文
5. **`Dataset` 实现**：系统级独立模块，支持 SQLiteAdapter 和 HttpAdapter。lib 文件通过 `from src.runtime.lib.dataset import Dataset` 直接导入。
6. **`InstanceLoader` 扩展**：解析 `.instance.yaml` 时加载 `bindings` 字段。

## 错误处理

| 场景 | 行为 |
|------|------|
| lib 中访问 `self._context` 但未被注入 | `AttributeError`，由 lib 开发者负责（注入保证在 LibProxy 调用前完成） |
| 外部数据源连接失败 | Dataset 抛异常，由调用方（lib 或 behavior script）捕获处理 |
| binding key 在 instance 中不存在 | `AttributeError`（`this.bindings.xxx` 访问不存在 key），由 lib 处理 |

## 与已有系统的关系

```
Model (index.yaml)
├── behaviors: [...] → Agent Model → InstanceManager.create() → 标准 Instance
└── behaviors: []    → 普通 Model → 可被 ref 引用，也可实例化（若需要）
                         ↓
    Agent Instance (slm-01，来自 slab_manager Model)
    ├── 标准 Instance：behaviors、triggers、state machine
    ├── 实例声明中配置 bindings.{key} 数据源
    ├── behavior script 调用 lib.dao.xxx()
    ├── lib 通过 self._context["this"].bindings 获取配置
    ├── lib 调用 Dataset(cfg) 读写数据
    ├── Dataset 根据 cfg.type 选择 Adapter，自动处理 fieldMap
    ├── 通过 service 暴露查询接口给其他 Agent
    └── 通过 event_bus / dispatch 发布实体变更事件
```
