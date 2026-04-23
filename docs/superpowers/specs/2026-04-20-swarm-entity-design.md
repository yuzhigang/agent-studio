# Swarm 与数据实体设计

**日期**: 2026-04-20
**状态**: 定稿

## 背景与问题

Agent Studio 中，除了 `ladle`（钢包）、`crane`（天车）、`dispatcher`（调度员）这类**有行为、有状态机、常驻内存**的智能体外，还存在另一类实体：

- **板坯**（slab）：每日数千条，本质是业务数据记录，无行为
- **生产订单**（order）：按业务流程推进，状态变化由业务系统驱动
- **钢卷**（coil）：产出后归档，海量历史数据

这些实体的共同特征：
- 数量巨大（数万至百万级），不适合每个都作为独立 `Instance` 入内存管理
- 有明确的业务字段结构（钢种、宽度、厚度、状态...），需要高效的条件查询
- 数据可能来自外部系统（MES、ERP）或 world 的 SQLite 存储
- 需要被 Agent（如调度员、板坯管理员）查询、引用和传递

本设计解决：如何在**零新增系统级抽象**的前提下，让这类数据实体被 Agent 通过 lib 管理，同时保持查询效率和架构一致性。

## 核心原则

1. **零新概念**：Swarm 就是普通 Instance，数据实体就是普通 Model。系统不新增 `DataStore`、`EntityRegistry` 等概念。
2. **约定优于配置**：数据 Model 通过**无 behaviors / 无 states** 自动识别，无需用户显式声明类型。
3. **binding 即数据源**：Agent 实例通过**实例声明文件**中的 binding 配置数据源，key = modelId，支持 fieldMap。
4. **查询脚本化**：条件查询由 Agent 的 behavior 脚本自行实现（写 SQL 或调 API），系统不做统一查询引擎。

## 核心概念

### 术语表

| 术语 | 定义 |
|------|------|
| **Swarm** | 管理数据实体的普通 Instance，有 behaviors、triggers、state machine，和其他 Agent 无区别 |
| **数据 Model** | 无 behaviors、无 states/transitions 的 Model，定义数据实体的 attributes/variables schema |
| **数据实体** | 数据 Model 的运行时单条记录，**不是 Instance**，不注册到 InstanceManager |
| **Dataset Binding** | Agent 实例声明中的 binding，key = modelId，声明该 Agent 管理的数据集数据源 + fieldMap |

### 识别规则

`ModelLoader` 加载 model 后，自动判断类型：

```python
model_type = "data_model" if not model.get("behaviors") and not model.get("states") and not model.get("transitions") else "agent"
```

- **Agent Model**（如 `ladle`、`slab_manager`）：有 behaviors 或 states 或 transitions → 正常走 InstanceManager
- **数据 Model**（如 `slab`、`order`）：无 behaviors 且无 states 且无 transitions → 不可直接实例化，仅作为 schema 契约使用

> 此规则是**运行时内部判断**，用户写 model 时无需关心，不新增 `type` 字段。`ModelLoader` 将 `_model_type` 注入 model dict，`InstanceManager.create()` 据此拒绝数据 Model 的实例化。

## 数据 Model 定义

数据 Model 的格式与 Agent Model 完全一致，仅省略 behaviors/states：

```yaml
# agents/logistics/slab/model/index.yaml
$schema: https://agent-studio.io/schema/v2
metadata:
  version: "1.0"
  name: slab
  title: 板坯
  group: logistics

attributes:
  grade:
    type: string
    title: 钢种
    default: ""
  width:
    type: number
    title: 宽度
    x-unit: mm
  thickness:
    type: number
    title: 厚度
    x-unit: mm

variables:
  temperature:
    type: number
    title: 温度
    x-unit: "℃"
    x-category: metric
  location:
    type: string
    title: 当前位置
    default: ""
  status:
    type: string
    title: 业务状态
    default: "produced"
    enum: [produced, cooled, inspected, shipped]

links: {}
```

### 与 Agent Model 的关键差异

| | Agent Model (ladle) | 数据 Model (slab) |
|---|---|---|
| behaviors | 有定义 | 空或省略 |
| states/transitions | 有定义 | 空或省略 |
| 可实例化 | ✅ `InstanceManager.create()` | ❌ 不可直接实例化 |
| 运行时位置 | InstanceManager 内存缓存 | 不缓存，由 Agent 通过 binding 管理 |
| 数量级 | 少（几十） | 多（万级+） |

## Agent Model 定义

Agent 是**标准 Agent Model**，其 Model 定义方式与普通 Agent 完全一致——**不包含任何 binding 配置**：

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
  cacheCount: { type: number, default: 0 }

behaviors:
  - name: onTemperatureUpdated
    trigger:
      type: event
      name: external.slabTemperature
    actions:
      - type: runScript
        script: |
          # 通过 this.bindings.slab 获取实例级别的数据源配置
          cfg = this.bindings.slab
          conn = sqlite.connect(cfg.connection)
          conn.execute(
            f"UPDATE {cfg.table} SET {cfg.fieldMap.temperature} = ? WHERE {cfg.fieldMap.id} = ?",
            (payload.temperature, payload.slabId)
          )
          conn.commit()

  - name: onSlabProduced
    trigger:
      type: event
      name: production.slabProduced
    actions:
      - type: runScript
        script: |
          cfg = this.bindings.slab
          conn = sqlite.connect(cfg.connection)
          cols = [cfg.fieldMap.id, cfg.fieldMap.grade, cfg.fieldMap.width, cfg.fieldMap.temperature, cfg.fieldMap.status]
          placeholders = ", ".join(["?"] * len(cols))
          conn.execute(
            f"INSERT INTO {cfg.table} ({', '.join(cols)}) VALUES ({placeholders})",
            (payload.slabId, payload.grade, payload.width, payload.temperature, "produced")
          )
          conn.commit()
          event_bus.publish("slab.created", {"slabId": payload.slabId, "grade": payload.grade})

services:
  getSlab:
    description: 获取单个板坯详情
    input:
      slabId: { type: string }
    output:
      slab: { type: object }

  querySlabs:
    description: 条件查询板坯列表
    input:
      filters: { type: object }
      limit: { type: number, default: 50 }
    output:
      items: { type: array }
      total: { type: number }
```

## Agent 实例声明与 Dataset Binding

Agent 的 binding 配置在**实例声明文件**中，和现有实例的 variable binding 位于同一位置：

```yaml
# worlds/steel-plant-01/agents/roles/slab_manager/instances/slm-01.instance.yaml
id: slm-01
modelId: slab_manager

state: idle

metadata:
  name: 板坯管理员-01
  title: 一号产线板坯管理员

attributes:
  syncIntervalSec: 30

variables:
  lastSyncTime: ""

# Dataset Binding：声明此 Agent 实例管理的数据集
# key = modelId（数据 Model 的 name），value = 数据源配置
bindings:
  slab:
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
      createdAt: created_at

  coil:
    type: api
    endpoint: http://mes/api/coils
    fieldMap:
      id: coil_id
      grade: steel_grade
      weight: net_weight
```

### 为什么 binding 在实例声明中？

与现有架构一致：

| | 定义位置 | 内容 | 何时确定 |
|---|---|---|---|
| **Model**（模板） | `agents/roles/slab_manager/model/` | behaviors, services, attributes schema | 开发时 |
| **实例声明**（配置） | `worlds/xxx/agents/roles/slab_manager/instances/` | id, 初始状态, **bindings**, 初始变量值 | 部署时 |

- Model 定义"能做什么"（behaviors, services）
- 实例声明"具体配置是什么"（bindings 指向哪个 DB/API，初始变量值）

同一个 `slab_manager` Model 可以在不同 world 中实例化，每个实例连接不同的数据源：

```yaml
# world A 的 slab_manager：连接本地 SQLite
bindings:
  slab:
    type: sqlite
    connection: ./runtime.db

# world B 的 slab_manager：连接 MES API
bindings:
  slab:
    type: api
    endpoint: http://mes-prod/api/slabs
```

### Binding 语义说明

系统中有两种 binding，声明位置不同，语义不同，不会冲突：

| 模式 | 声明位置 | key 含义 | 用途 |
|------|---------|---------|------|
| **Instance Variable Binding** | 任意 `.instance.yaml` | 变量名（如 `temperature`） | 将外部数据源的单个字段绑定到 Instance 变量，系统定时同步 |
| **Dataset Binding** | Agent 的 `.instance.yaml` | modelId（如 `slab`） | 声明 Agent 实例管理的数据集数据源配置，由 behavior 脚本使用 |

## 数据实体存储策略

数据实体的存储位置**由 Agent 实例的 binding 配置决定**，系统不做强制统一。

### 场景 1：存储在 world 的 runtime.db

```yaml
bindings:
  slab:
    type: sqlite
    connection: ./runtime.db
    table: slabs
```

- 表由 Agent 的 behavior 脚本自行创建（`CREATE TABLE IF NOT EXISTS`）
- 字段按 `fieldMap` 映射到数据 Model 的 attributes/variables
- 查询直接在 `runtime.db` 上执行 SQL

### 场景 2：存储在外部 SQLite

```yaml
bindings:
  slab:
    type: sqlite
    connection: /data/mes/slab.db
    table: t_slab
```

- 连接外部数据库文件
- 通过 `fieldMap` 映射外部字段名到 Model 字段名

### 场景 3：存储在外部 API

```yaml
bindings:
  coil:
    type: api
    endpoint: http://mes/api/coils
    method: GET
    auth:
      type: bearer
      token: "${env.MES_TOKEN}"
    fieldMap:
      id: coil_id
      grade: steel_grade
```

- behavior 脚本通过 HTTP 调外部 API
- `fieldMap` 映射 API 响应字段到 Model 结构

## FieldMap 机制

`fieldMap` 是连接**外部数据源字段**与**Model schema** 的桥梁。

```yaml
fieldMap:
  id: slab_no              # Model.id ← 外部表.slab_no
  grade: steel_grade       # Model.grade ← 外部表.steel_grade
  width: w                 # Model.width ← 外部表.w
  temperature: temp        # Model.temperature ← 外部表.temp
  location: current_pos    # Model.location ← 外部表.current_pos
  status: state            # Model.status ← 外部表.state
```

### 使用方式

```python
# behavior 脚本中，通过 this.bindings.{modelId}.fieldMap 访问
fm = this.bindings.slab.fieldMap

# 读取：外部字段 → Model 字段
external_row = {"slab_no": "S001", "steel_grade": "Q235B", "w": 1200}
slab = {
    "id": external_row[fm.id],
    "grade": external_row[fm.grade],
    "width": external_row[fm.width],
}

# 写入：Model 字段 → 外部字段
update_sql = f"UPDATE {this.bindings.slab.table} SET {fm.grade}=?, {fm.width}=? WHERE {fm.id}=?"
conn.execute(update_sql, (payload.grade, payload.width, payload.slabId))
```

### fieldMap 默认值

若省略 `fieldMap`，默认采用**同名映射**：

```yaml
# 省略 fieldMap 时，等同于：
fieldMap:
  id: id
  grade: grade
  width: width
  ...
```

### 反向映射（外部字段 → Model 字段）

读取外部数据（API/SQL）时，需要将外部字段名映射回 Model 字段名：

```python
fm = this.bindings.slab.fieldMap

# 读取 API 响应或 SQL 结果
external_row = {"slab_no": "S001", "steel_grade": "Q235B", "w": 1200}

# 反向映射：外部字段名 → Model 字段名
# 通过 _reverse 属性获取反向字典
rev = fm._reverse  # {"slab_no": "id", "steel_grade": "grade", "w": "width", ...}
slab = {
    rev["slab_no"]: external_row["slab_no"],
    rev["steel_grade"]: external_row["steel_grade"],
    rev["w"]: external_row["w"],
}
# 结果: {"id": "S001", "grade": "Q235B", "width": 1200}
```

### SQL 安全提示

使用 `fieldMap` 构建 SQL 时，**表名和列名应做标识符校验**，防止意外注入：

```python
# ✅ 正确：列名来自 fieldMap（受控），值用参数化
cols = [cfg.fieldMap.grade, cfg.fieldMap.width]
conn.execute(f"UPDATE {cfg.table} SET {cols[0]}=?, {cols[1]}=? WHERE {cfg.fieldMap.id}=?",
             (payload.grade, payload.width, payload.slabId))

# ❌ 错误：直接将用户输入拼接到 SQL
conn.execute(f"UPDATE {payload.table} SET {payload.column}=? WHERE id=?")  # 危险！
```

`fieldMap` 中的键（Model 字段名）由 model 定义保证安全；值（外部字段名）由实例声明配置控制。behavior 脚本不应将不可信输入用作表名或列名。

## Dataset 工具类

Dataset 是**系统级独立组件**，用于统一封装不同数据源类型的访问逻辑。它不属于 lib，也不属于 shared lib——它是一个独立的运行时工具，由 lib 或 behavior script 按需调用。

### 设计定位

```
Dataset（系统级工具类）
├── 输入：binding 配置（type, connection, table, fieldMap...）
├── 内部：根据 type 自动选择 Adapter
│   ├── sqlite → SQLiteAdapter（连接池、参数化查询）
│   ├── api    → HttpAdapter（HTTP 请求、响应解析）
│   └── 未来可扩展：mysql、redis、kafka...
└── 输出：统一的数据操作方法
```

**核心价值**：binding 的数据源类型发生变化时（如 SQLite → API），lib 中读取数据的逻辑无需修改。

### 使用方式

```python
# 在 lib 或 behavior script 中使用
from dataset import Dataset

cfg = this.bindings.slab
ds = Dataset(cfg)

# 查询
slabs = ds.query({"status": "produced"}, limit=100)

# 单条获取
slab = ds.get("slab-001")

# 创建
ds.create({"id": "slab-002", "grade": "Q345B", "width": 1500})

# 更新
ds.update("slab-001", {"status": "shipped"})

# 删除
ds.delete("slab-001")

# 计数
count = ds.count({"grade": "Q235B"})
```

### 注入方式

Dataset 作为**预加载模块**注入沙箱：

```python
# src/runtime/lib/sandbox.py
PRELOADED_MODULES = {
    "math", "random", "statistics", ..., "dataset",  # 新增
}
```

这样 behavior script 和 lib 中都能直接 `from dataset import Dataset` 或 `import dataset`。

### 与 lib 的关系

| 组件 | 层级 | 职责 | 关系 |
|------|------|------|------|
| Dataset | 系统级 | 统一封装数据源访问 | 独立存在，可被任何代码调用 |
| lib (dao.py) | 用户层 | 业务查询逻辑（如 `getSlabs`、`getSlab`） | 调用 Dataset，但不依赖具体 Adapter |
| binding | 配置层 | 声明数据源类型和连接信息 | 作为参数传给 Dataset |

### 示例：binding 类型变化时 lib 无需修改

```python
# lib 中的代码——与数据源类型无关
class SlabDAO:
    @lib_function(name="getSlabs", namespace="slab_manager")
    def get_slabs(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)  # 自动识别 type=sqlite 或 type=api
        return ds.query(args.get("filters", {}), args.get("limit", 50))
```

无论 instance.yaml 中 `slab` binding 的 `type` 是 `sqlite` 还是 `api`，`SlabDAO.get_slabs()` 的逻辑都不需要改动。

## 跨 Agent 交互

### 方式 1：Service 调用（请求-响应）

```yaml
# dispatcher behavior 中调用 slab_manager 的 service
target: slm-01
service: querySlabs
input:
  filters:
    grade: "Q235B"
    status: "produced"
  limit: 10
```

与其他 Agent 的 service 调用方式完全一致。

### 方式 2：事件订阅（发布-订阅）

```yaml
# ladle behavior 中订阅 slab 事件
behaviors:
  - name: onSlabReady
    trigger:
      type: event
      name: slab.statusChanged
      when: payload.toStatus == "ready_for_transport"
    actions:
      - type: runScript
        script: |
          # 获取板坯详情
          slab = call_service("slm-01", "getSlab", {"slabId": payload.slabId})
          # 指派天车
          event_bus.publish("crane.assignTask", {
            "targetSlab": payload.slabId,
            "destination": slab.location
          })
```

### 实体引用方式

数据实体不是 Instance，无法直接通过 `links` 引用。引用方式：

```yaml
# ladle behavior 中记录当前装载的板坯
variables:
  loadedSlabs: []  # 存实体 ID 列表

# 需要实体详情时，通过 Agent 查询
slab_info = call_service("slm-01", "getSlab", {"slabId": variables.loadedSlabs[0]})
```

## Agent 多实体管理

一个 Agent 实例可以管理多种数据实体，通过多个 dataset binding 声明：

```yaml
# worlds/xxx/agents/roles/production_manager/instances/pm-01.instance.yaml
id: pm-01
modelId: production_manager

bindings:
  order:
    type: sqlite
    connection: ./runtime.db
    table: production_orders
    fieldMap:
      id: order_no
      status: order_status

  slab:
    type: sqlite
    connection: ./runtime.db
    table: slabs
    fieldMap:
      id: slab_no

  coil:
    type: api
    endpoint: http://mes/api/coils
```

```python
# behavior 脚本中分别访问
orders = query_table(this.bindings.order, "SELECT * FROM ...")
slabs = query_table(this.bindings.slab, "SELECT * FROM ...")
```

## 与已有系统的关系

```
Model (index.yaml)
├── behaviors: [...] → Agent Model → InstanceManager.create() → 标准 Instance（缓存、triggers、state machine）
└── behaviors: []    → 数据 Model → 不可实例化
                         ↓
                    作为 schema 契约
                         ↓
    Agent Instance (slm-01，来自 slab_manager Model)
    ├── 标准 Instance：behaviors、triggers、state machine
    ├── 实例声明中配置 bindings.{modelId} 数据源
    ├── 通过 this.bindings.{modelId} 访问外部数据源
    ├── 通过 fieldMap 做字段映射
    ├── 通过 service 暴露查询接口给其他 Agent
    └── 通过 event_bus 发布实体变更事件
```

## 数据 Model 目录结构

数据 Model 与 Agent Model 共享相同的目录结构：

```
agents/
  logistics/
    ladle/
      model/              ← Agent Model（有 behaviors）
        index.yaml
        behaviors.yaml
      instances/          ← ladle 的静态实例声明
        ladle-01.instance.yaml
    slab/
      model/              ← 数据 Model（无 behaviors）
        index.yaml        # 只有 attributes/variables，无 behaviors/states
      # 数据 Model 不需要 instances/ 目录（不可直接实例化）
  roles/
    slab_manager/
      model/
        index.yaml        # Agent Model（有 behaviors、services）
        behaviors.yaml
      instances/          ← Agent 的实例声明
        slm-01.instance.yaml   # 配置 dataset bindings
```

## 启动校验

`WorldRegistry.load_world()` 阶段，系统对 Agent 实例进行以下校验：

1. **Dataset Binding 引用校验**：每个 `bindings.{modelId}` 中，key 必须引用一个已加载的数据 Model（`_model_type == "data_model"`）。若未找到，**启动时抛异常**。
2. **FieldMap 覆盖校验**：`fieldMap` 必须至少包含 `primaryKey` 对应的 Model 字段映射。若缺失，**启动时抛异常**。
3. **Binding 冲突检测**：两个 Agent 实例不可声明同名 `modelId` 的 dataset binding。若检测到冲突，**启动时抛异常**。
4. **Link 引用校验**：Agent Model 的 `links` 中如果 `targetType` 指向数据 Model，启动时警告（数据实体不是 Instance，无法直接 link）。

## 错误处理

| 场景 | 行为 |
|------|------|
| 尝试 `create()` 数据 Model | `InstanceManager` 抛异常：`"Data model 'slab' cannot be instantiated directly. Use a Agent agent to manage."` |
| Agent 实例的 dataset binding 引用了不存在的 modelId | **启动时抛异常**，阻止 world 加载 |
| fieldMap 中缺失 primaryKey 映射 | **启动时抛异常** |
| fieldMap 中其他 Model 字段缺失映射 | 运行时访问报 KeyError，由 behavior 脚本处理 |
| 外部数据源连接失败 | 由 behavior 脚本捕获异常，可触发告警事件 |
| 两个 Agent 实例的 dataset binding 冲突（同一 modelId） | **启动时抛异常** |

## 实施要点

1. **`ModelLoader` 修改**：加载后自动判断 `_model_type`（`agent` / `data_model`），写入 model dict 元数据。无需将 `bindings` 加入 `known_keys`（binding 不在 Model YAML 中声明，在实例声明文件中）。
2. **`InstanceManager` 修改**：`create()` 时检查 `model.get("_model_type")`，拒绝直接实例化 `data_model`。
3. **`InstanceLoader` 修改**：解析 `.instance.yaml` 时，识别 dataset binding（key 不是变量名，而是 modelId）。需要区分：
   - 变量 binding：`bindings.{variableName}` 有 `source`、`path`、`selector`、`transform`
   - dataset binding：`bindings.{modelId}` 有 `type`、`connection`、`table`、`fieldMap`
4. **`WorldRegistry` 修改**：`load_world()` 阶段：
   - 先加载所有 Model（含数据 Model）
   - 再加载所有实例声明（含 Agent 实例的 dataset bindings）
   - 校验 dataset binding 引用存在性、fieldMap 完整性、冲突检测
5. **Sandbox 上下文扩展**：`_build_behavior_context` 将当前 Instance 的 dataset bindings 注入为 `this.bindings` 命名空间（与变量 binding 合并），含 `fieldMap` 和 `_reverse`。
6. **Dataset 预加载**：将 `dataset` 模块加入 `SandboxExecutor.PRELOADED_MODULES`，behavior script 和 lib 中可直接 `from dataset import Dataset`。
7. **LibContext 注入**：`LibProxy` 在调用 lib 函数前，将 `LibContext`（`this`、`payload`、`source`、`dispatch`、`world_state`）注入到 lib class 实例的 `_context` 属性中，lib 函数通过 `self._context` 访问运行时信息。

## 附录：完整示例

### slab_manager Agent Model

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
  cacheCount: { type: number, default: 0 }

behaviors:
  - name: syncFromMES
    trigger:
      type: timer
      interval: 30000
    actions:
      - type: runScript
        script: |
          cfg = this.bindings.slab
          # ... API 调用逻辑

  - name: onSlabStatusChanged
    trigger:
      type: event
      name: external.slabStatusUpdate
    actions:
      - type: runScript
        script: |
          cfg = this.bindings.slab
          conn = sqlite.connect(cfg.connection)
          conn.execute(
            f"UPDATE {cfg.table} SET {cfg.fieldMap.status} = ? WHERE {cfg.fieldMap.id} = ?",
            (payload.status, payload.slabId)
          )
          conn.commit()
          event_bus.publish("slab.statusChanged", {
            "slabId": payload.slabId,
            "fromStatus": payload.oldStatus,
            "toStatus": payload.status
          })

services:
  getSlab:
    description: 获取板坯详情
    input:
      slabId: { type: string }
    output:
      slab: { type: object }

  querySlabs:
    description: 查询板坯列表
    input:
      filters: { type: object }
      limit: { type: number, default: 50 }
      offset: { type: number, default: 0 }
    output:
      items: { type: array }
      total: { type: number }
```

### slab_manager 实例声明（含 dataset bindings）

```yaml
# worlds/steel-plant-01/agents/roles/slab_manager/instances/slm-01.instance.yaml
id: slm-01
modelId: slab_manager

state: idle

metadata:
  name: 板坯管理员-01
  title: 一号产线板坯管理员

attributes:
  syncIntervalSec: 30

variables:
  lastSyncTime: ""

bindings:
  # Dataset Binding：声明此 Agent 管理的数据集
  slab:
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

### slab_manager lib (dao.py)

```python
# agents/roles/slab_manager/libs/dao.py
from src.runtime.lib.decorator import lib_function
from dataset import Dataset


class SlabDAO:
    @lib_function(name="getSlabs", namespace="slab_manager")
    def get_slabs(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.query(args.get("filters", {}), args.get("limit", 50))

    @lib_function(name="getSlab", namespace="slab_manager")
    def get_slab(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.get(args.get("slabId"))

    @lib_function(name="updateSlab", namespace="slab_manager")
    def update_slab(self, args):
        cfg = self._context["this"].bindings.slabs
        ds = Dataset(cfg)
        return ds.update(args.get("slabId"), args.get("data"))
```

### slab 数据模型

```yaml
# agents/logistics/slab/model/index.yaml
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

# 无 behaviors，无 states → 自动识别为 data_model
```
