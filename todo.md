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
