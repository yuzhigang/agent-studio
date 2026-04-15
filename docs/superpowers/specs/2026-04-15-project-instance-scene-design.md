# Project-Instance-Scene 架构设计文档

## 1. 背景与目标

在 `ModelLoader` 支持目录化拆分之后，Agent 的**静态定义**（Model）已经具备良好的可维护性。本设计解决的是**运行时实例**如何组织、隔离和持久化的问题。

目标：
- 支持同一 Model 生成多个实例（静态预置 + 动态生成）。
- 支持多个 Scene 对同一批实例进行共享观察或隔离仿真。
- 明确高频变化变量（metric）与业务状态变量（state）的差异化持久化策略。

---

## 2. 核心概念定义

| 概念 | 定义 |
|---|---|
| **Model** | Agent 的静态配置模板，由 `ModelLoader` 从 `model/` 目录或 `model.yaml` 加载。 |
| **Instance** | Model 的运行时实体，具有全局唯一 `instanceId`。 |
| **Project** | 一个完整工厂/产线的数字化镜像，包含全局实例池、全局配置、Scene 集合。 |
| **Scene** | Project 内的一个**运行视图或仿真上下文**，可引用 Project 实例，也可挂载私有临时实例。 |

---

## 3. 实例作用域分层

实例根据创建位置和生命周期，分为两类：

### 3.1 Project 实例（全局共享）
- **作用域**：`scope: "project"`
- **生命周期**：随 Project 启停而创建/销毁。
- **可见性**：可被任意 Scene 通过 `references` 引用。
- **示例**：建厂时确定的设备（`ladle-001` ~ `ladle-012`），以及 Project 运行过程中动态生成的物料（`slab-20250415-08921`）。

### 3.2 Scene 实例（局部私有）
- **作用域**：`scope: "scene:<scene-id>"`
- **生命周期**：随 Scene 启停而创建/销毁。
- **可见性**：仅对创建它的 Scene 可见，其他 Scene 无法访问。
- **示例**：应急演练场景中临时注入的质检机器人 `temp-inspector-01`。

---

## 4. 动态实例策略

**只保留单一 Model 模板**，实例差异通过运行时参数区分：

- `slab` 作为一个 Model 目录存在（`agents/logistics/slab/model/`）。
- 动态实例通过工厂创建，传入覆盖的 `attributes` 和 `variables`：
  ```python
  instance_manager.create(
      model_name="slab",
      instance_id="slab-20250415-08921",
      attributes={"grade": "Q235B"},
      variables={"temperature": 1250}
  )
  ```
- **禁止**为每类细微差异都新建一个 Model 目录，避免 `agents/` 目录爆炸。

---

## 5. Scene 模式：Shared vs Isolated（CoW）

每个 Scene 必须声明自己的运行模式：

### 5.1 `shared` 模式
- 直接引用 Project 实例的**真实内存状态**。
- 任何 Scene 内的修改都会立即影响其他引用该实例的 Scene。
- **适用场景**：监控面板、多视角观察真实产线。

### 5.2 `isolated` 模式（Copy-on-Write）
- Scene 启动时，对引用的 Project 实例做**内存快照（shallow copy）**。
- Scene 内的读写只操作副本，不影响 Project 全局状态。
- **适用场景**：仿真、培训、what-if 分析。

```yaml
scene:
  sceneId: "emergency-drill"
  mode: "isolated"
  references:
    - "ladle-001"
    - "slab-08921"
  localInstances:
    temp-inspector-01:
      modelName: "inspector"
      variables:
        targetLadle: "ladle-001"
```

---

## 6. 状态持久化策略

基于 Model 中 `variables` 的 `x-category` 字段做差异化处理：

| 类别 | 含义 | 持久化策略 |
|---|---|---|
| `state` | 业务状态变量，变化慢，状态机依赖 | **随实例快照写数据库** |
| `metric` | 遥测变量，高频变化，纯观测值 | **写时序数据库** |

### 6.1 实例快照结构（DB）
```yaml
instanceId: "ladle-001"
modelName: "ladle"
modelVersion: "2.0"
scope: "project"
state:
  current: "full"
  enteredAt: "2026-04-15T10:00:00Z"
variables:
  steelAmount: 180        # state 类变量
  processStatus: "awaiting_transport"
links:
  assignedCaster: "caster-03"
audit:
  version: 152
  updatedAt: "2026-04-15T10:00:00Z"
  lastEventId: "evt-uuid-789"
```

### 6.2 Isolated Scene 的 Metric 回填

当 `isolated` 模式 Scene 启动时：
1. 从 DB 加载 Project 实例的 `state` 类变量快照。
2. `metric` 类变量从时序数据库读取**最近一次数据点**进行回填。
3. 若时序库无数据，则使用 Model 定义的 `default` 值。

---

## 7. 关键运行流程

### 7.1 Scene 启动（`isolated` 模式）

1. **引用完整性校验**
   - 对每个 `references` 中的实例，检查其 `links` 指向的目标是否也在本 Scene 中。
   - 缺失的目标若存在于 Project 全局池中，**自动拉入** `references`。
   - 若 Project 池中也不存在，抛出 `SceneConfigError`。

2. **CoW 快照复制**
   - 复制 Project 实例的内存状态到 Scene 私有空间。

3. **Metric 回填**
   - 从时序库补全 `metric` 类变量的最新值。

4. **创建 Local Instances**
   - 加载对应 Model，按提供的参数初始化 Scene 私有实例。

5. **Property Reconciliation**
   - 对所有实例（引用 + local）重算 `derivedProperties`。

6. **启动 Scene 事件总线**
   - 隔离模式下，事件总线**仅连接 Scene 内部实例**。

### 7.2 实例状态变更

```python
# shared 模式：直接修改 Project 实例
ladle_001.state.current = "maintenance"

# isolated 模式：只修改 Scene 的 CoW 副本
scene_copy_of_ladle_001.state.current = "maintenance"
# Project 实例不受影响
```

### 7.3 消息/事件边界

隔离模式 Scene 有严格的消息边界：

```python
def publish_event(scene, event):
    if scene.mode == "isolated" and event.target not in scene.instances:
        raise SceneBoundaryError(
            f"Isolated scene cannot send event to external instance: {event.target}"
        )
    # 继续路由...
```

这意味着：
- `local` 实例的行为副作用**不会逃逸**到 Project 或其他 Scene。
- Scene 关闭时，只需销毁内部事件总线和 CoW 副本即可，无需清理外部状态。

---

## 8. 与现有 Model 抽象的对接

| 现有模块 | 职责 | 是否需要修改 |
|---|---|---|
| `ModelLoader` | 加载静态 Model 定义 | **否**，继续负责纯定义加载 |
| `LibRegistry` | 扫描 `libs/` 并注册脚本函数 | **否**，实例通过 `modelName` 解析到 `agents/` 下的 `libs/` |
| `SandboxExecutor` | 沙箱执行脚本 | **未来可能需要扩展**，传入 `sceneContext` 让脚本感知自身作用域 |
| **新增 `InstanceManager`** | 管理 Project/Scene 的实例生命周期、CoW、持久化 | **新增** |
| **新增 `SceneController`** | 负责 Scene 启动、校验、事件边界、清理 | **新增** |

---

## 9. 设计决策记录

### 决策 1：去掉 Fleets 层
- **原因**：在当前复杂度下，Fleet 只是实例的逻辑分组，可以用标签或查询条件替代，无需作为一级概念引入。若未来实例数量达到管理瓶颈，再考虑引入。

### 决策 2：Scene 默认消息隔离
- **原因**：隔离模式的核心用途是仿真和 what-if 分析，如果消息能逃逸到外部，会导致 Project 真实状态被污染，仿真失去意义。

### 决策 3：Derived Properties 恢复后强制重算
- **原因**：`derivedProperties` 是纯计算值，不持久化。实例从快照恢复时，必须保证在第一帧状态机运行前完成重算，否则 behaviors/rules 可能读到过期或缺失值。

### 决策 4：动态实例采用单一 Model 模板
- **原因**：避免 `agents/` 目录爆炸。实例差异应通过运行时参数（`attributes` + `state` 类 `variables`）表达，而非静态 Model 文件。

---

## 10. 后续待设计事项

- `InstanceManager` 和 `SceneController` 的接口契约与 Python 类设计。
- `metric` 变量到时序数据库的写入频率和聚合策略（秒级、分钟级、变化阈值触发）。
- `isolated` Scene 的 CoW 实现细节（深拷贝 vs 写时复制页）。
