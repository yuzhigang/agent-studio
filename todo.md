# 特性规划

## Instance 生命周期回调机制
**目标**：在 Instance 被加载到内存和从内存中移除时，提供用户可介入的钩子。
- `onActivate`：Instance 首次从持久存储加载到内存时触发（如懒加载、场景启动、状态恢复），用户可以执行初始化逻辑。
- `onDeactivate`：Instance 从内存中移除前触发（如场景停止、实例过期），用户可以执行清理或刷新状态。

**目的**：
1. 降低 Instance 在内存中的常驻压力——长时间未被访问的实例可以被卸载，下次访问时再恢复，减少内存占用。
2. 让用户能表达"加载时自动初始化"和"销毁前自动清理"的逻辑，而不是依赖外部事件去驱动。

---

## Service 请求-响应调用语义（`invoke`）
**目标**：补全运行时中 `services` 设计的 request-response 调用能力。

**现状**：AGENT.md 已明确定义 `services` 是 "agent 可被调用的命令面"（第 4.2 节），但当前运行时的 `SandboxExecutor` 只向行为脚本注入了 `dispatch` 函数——它是 fire-and-forget 的事件发布，没有返回值，也无法定向调用另一个 Agent 的 service。服务调用端缺少 `invoke` 函数。

**需要实现**：
- `invoke(target, service_name, params) -> result`：向目标 Agent 的 service 发送请求，同步等待执行结果。
- 超时机制：目标未在指定时间内响应则抛出超时异常。
- 目标 Agent 侧 service 执行完毕后，将返回值回传给调用方。

**目的**：
1. 让 AGENT.md 中定义的 `services` 设计真正落地——使其成为 Agent 间"互相询问、获取数据、委托操作"的一等接口。
2. 降低行为脚本中手动维护"发起事件 → 等待回调事件"状态机的复杂度（当前必须用变量来跟踪请求上下文）。
3. 让 Instance 之间可以直接调用 service（如调度 Agent 调用订单管理员的 `getOrder`），而不需要引入临时的回调事件行为来拼凑流程。

---

## RefVar 透明引用代理（Lazy Reference）
**目标**：在 Agent 模型中支持声明对外部数据集的透明引用，用户操作 `this.orders` 时完全感知不到它是惰性加载的外部数据。

**设计要点**：
- Model YAML 中通过 `type: reference` + `resolver` 声明引用，如：
  ```yaml
  variables:
    orders:
      type: reference
      resolver: orderStore.query
      params: {status: active}
  ```
- 行为脚本中 `this.orders['001']` 第一次访问时，resolver 自动触发加载；看起来像普通 dict，无需显式 `load()`。
- 行为脚本执行完毕后，`SandboxExecutor` 自动对比加载时的快照与当前数据，只写回 diff。
- 支持嵌套修改追踪（快照 diff 策略）。

**目的**：
1. 让聚合管理员模式（如订单管理员）可以管理大量领域对象，同时保持 Checkpoint 经济——checkpoint 只存引用条件或 diff，不存全量数据。
2. 避免运行时因大量领域对象升格为独立 Instance 而导致内存和 EventBus 订阅爆炸。
3. 用户写行为脚本时不需要理解"引用 vs 数据容器"的区别，降低心智负担。

---

## Agent 世界模型三分法（Role / Thing / Concept）
**目标**：在统一的 Agent 抽象下，通过存在论分类表达不同智能体在世界中的本体地位，帮助用户在建模时做出正确的归属判断。

**哲学根基**：对应真实世界的三种基本存在方式——人、物、概念。

| 分类 | 存在方式 | 核心直觉 | 典型例子 |
|------|---------|---------|---------|
| **`Role`** | 人（主体） | 能动的、承担职能的、有决策能力的 | 调度员、操作员、审批人 |
| **`Thing`** | 物（客体） | 占据空间的、有物理属性的、可被感知的 | 钢包、天车、传感器、仓库 |
| **`Concept`** | 概念（建构） | 抽象的、社会约定的、不占据物理空间的 | 订单、合同、组织、申请单、预算 |

**归类边界**：
- `Thing` 包含物理实体及其聚合（产线、仓库）——它们有空间属性（坐标、边界、容量）。
- `Role` 的锚点是**人**，不是抽象的职能标签。张三可以是调度员（Role），也可以切换为操作员（另一个 Role）。组织（采购部、项目组）不是 Role，是 `Concept`——它是抽象的社会建构。
- `Concept` 不是 Object/Entity 的别名——那两类词在编程语境中"包含一切"，失去区分意义。`Concept` 明确表达"非人、非物"。
- 生产批次、运输任务等看似"过程性"的对象，归为 `Concept`——它们的"时间展开"只是状态机流转（`startedAt` / `currentState` / `estimatedEnd`），时间是状态的属性，不是独立的存在论范畴。

**目的**：
1. 让用户在建模时凭直觉就能判断"这个东西是什么"，从而决定它应该有哪些 links 语义和行为预期。
2. 统一 schema：三类 Agent 底层完全平等（都有 `states`、`links`、`services`、`behaviors`），但 `category` 标签提供了心理预期，使 `links` 的 relation 语义和生命周期设计更自然。
3. 避免 Palantir 式"一切平级本体"带来的建模混乱，同时保留 Agent 抽象的统一性。

---

- [ ] Alarm history cleanup on instance deletion: when an instance is removed/archived,
      decide whether to cascade-delete its alarm records or keep them for audit.
      Currently alarms table retains records even after instance removal.

---

# 架构漏洞修复清单 (2026-04-24)

按优先级排列，标注涉及文件。

## 🔴 Bug：必须修复

### 1. 级联触发 (Cascading triggers) 无防护
- **文件**: `src/runtime/instance_manager.py:214-228`, `trigger_registry.py:64-67`
- **问题**: behavior 修改 property → notify_value_change → 触发下级 behavior → 无限递归。无深度限制、无循环检测。
- **方向**: notify_value_change 加 `depth > MAX_DEPTH` 拦截，或记录 `(instance_id, trigger_id)` 防重入。

### 2. Alarm 状态重启丢失
- **文件**: `src/runtime/alarm_manager.py`
- **问题**: `_states` 纯内存，`_persist_alarm_state` 写了 store 但无 `load/restore` 方法。World 重启后所有 alarm 回到 inactive。
- **方向**: AlarmManager 增加 `restore(world_id)`，StateManager checkpoint/restore 纳入 alarm 状态。

## 🟠 设计缺口：需要补全

### 3. Worker 端无 WebSocket 重连逻辑
- **文件**: `src/worker/cli/run_command.py:180-234`
- **问题**: WebSocket 断开连接后缺少重连初始化确认，导致状态不同步。
- **方向**: run_supervisor_client 外层已有重试，但重连后需增加完整初始化确认流程。

### 4. Condition window 未实现
- **文件**: `src/runtime/triggers/condition_trigger.py`
- **问题**: time-sliding / count-sliding / tumbling 三种 window 均未实现，参数静默忽略。
- **方向**: 实现 window 逻辑，或注册时检测参数抛 NotImplementedError。

### 5. 缺少可观测性基础设施
- **文件**: 全局
- **问题**: 无结构化日志、无事件追踪、无性能指标。调试级联触发和 behavior 执行困难。
- **方向**: 关键路径加 logging（trigger_registry、alarm_manager、instance_manager._execute_actions）。

### 6. `asyncio.Lock` vs `threading.RLock` 混用 ✅
- **文件**: `event_bus.py:11`, `instance_manager.py:113`, `supervisor/worker.py:24`, `trigger_registry.py`
- **已处理**:
  - `InstanceManager.get()`: 将 I/O（`_store.load_instance`）移到锁外，锁内只保留快速 dict 操作。锁类型保持 `threading.Lock`（被 `to_thread` 回调调用）。
  - `TriggerRegistry`: 补充了 `threading.Lock`（之前完全无锁）。`notify_value_change` 被同步 sandbox 路径调用，不能用 `asyncio.Lock`。
  - `EventBus`: `threading.RLock` 保留（`publish()` 经由 sandbox `dispatch()` 以同步方式调用）。
  - `WorkerController`: 已使用 `asyncio.Lock` ✅
  - 关键约束：`publish()` / `notify_value_change` / `get()` 等路径同时运行在同步 sandbox 和异步 handler 中，无法统一为 `asyncio.Lock`。

### 7. ValueChangedTrigger 已移除 ✅
- **变更**: `ValueChangedTrigger` 类、`tests/runtime/test_value_changed_trigger.py` 已删除。
- **原因**: O(n²) 源于 ValueChangedTrigger 线性扫描所有 entry；O(n) 的 TriggerRegistry 层遍历（仅 4 个 impl）不是瓶颈。
- **后续**: 配合 `dependOn` 统一路线，条件触发机制在未来重新设计。

## 🟡 可改进

### 8. AlarmManager force_clear 不校验 alarm 存在性
- **文件**: `alarm_manager.py:154-174`
- **问题**: `_get_alarm_config` 返回 `{}` 时仍发布残缺的 clear 事件。

### 9. Scene.stop 不等待活跃 behavior
- **文件**: `scene_manager.py`
- **问题**: 强制停止可能留下半修改的实例状态。无超时回收。

### 10. InstanceManager.create() 缺少 data_model 校验
- **文件**: `instance_manager.py`
- **问题**: 设计规定 `_model_type == "data_model"` 禁止创建实例，但 create() 未做此校验。
