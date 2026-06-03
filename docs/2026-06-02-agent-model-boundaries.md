# Agent Studio 模型边界与项目定位思考

本文档整理了针对 Agent Studio 项目目标、三类模型边界，以及内生仿真能力的讨论结果。它不是最终 schema 设计稿，而是后续架构收敛的约束基础。

## 1. 项目存在的意义

这个项目如果按最初目标重新定义，本质上不是“做一个通用 agent 平台”，而是：

**为工业现场建立一个统一、可运行、可推理、可协作的 agent world model。**

这个世界里存在三类不同性质的对象：

- `thing`：物理世界中的装置、设备、容器、运输单元
- `role`：调度员、工艺员、班长、操作员等业务角色的智能体
- `concept`：订单、浇次、任务等业务语义对象

它们共享同一个 world、同一套关系网络、同一套审计体系，但不共享同一种主动性。

### 1.1 两类 agent 的原始设想

项目最初期望的 agent 有两类：

1. `thing agent`
   它们存在于物理世界，偏机械、偏确定性，更像根据配置好的信息和规则去响应式执行动作函数。

2. `role agent`
   它们代表不同角色的人，更接近 LLM 驱动的智能体，需要深度思考、决策、调用工具并执行。它们可以获取各种 `thing agent` 的信息，作为思考和决策上下文。

### 1.2 进一步补出的第三类：concept

除了 `thing` 和 `role`，还需要一类抽象业务对象：

- `ProductionOrder`
- `CastingPlan`
- `Heat`
- `TransportTask`

这类对象不是物理设备，也不是主动决策主体，但它们承载了 agent 之间共享的业务语义。

## 2. 内生仿真能力的判断

对“当前智能体太依赖外部驱动，看起来不活”的判断是成立的。

例如一个转炉，在收到“铁包到达”事件后，按业务理解不应只是停在那里等待外界继续喂事件，而应具备一定的内生过程演化能力，例如：

- 根据等待时间分布生成“兑铁开始”
- 再根据时间分布生成“加废钢开始”
- 再生成“出钢开始”

这类过程本质上是设备或工艺本身的内生演化。

### 2.1 正确的方向

应该让智能体具备一定的内生仿真能力，否则 `thing` 只是被动状态机，世界会显得很假。

### 2.2 需要避免的问题

但不应让每个智能体各自私有地掌控未来事件和仿真时间轴，否则会带来：

- 全局时间不一致
- 资源冲突无法统一处理
- 前置条件失效后无法统一取消未来事件
- 上下游联动失真

### 2.3 推荐结论

推荐采用混合式设计：

1. `thing` 定义自己的内生过程规则
2. `simulation scheduler` 或全局仿真引擎统一调度未来事件
3. `runtime` 继续负责消费事件并执行状态变更

一句话概括：

**要补的是“内生过程仿真层”，而不是简单地让每个 agent 自己随意发未来事件。**

## 3. 三类对象的总边界

系统中应明确存在三类世界对象：

- `thing`：物理执行体
- `role`：决策与指挥体
- `concept`：被管理的业务语义对象

总原则：

- `thing` 负责真实执行和状态演化
- `role` 负责观察、判断、下命令并闭环执行
- `concept` 负责表达业务语义和生命周期

这三者不应被强行塞进“同一种主动 agent”抽象里。

## 4. thing 的职责边界

### 4.1 定义

`thing` 是存在于物理世界中的装置、容器、运输单元、工位或设备。

### 4.2 职责

- 表达物理状态
- 表达可执行能力
- 接收命令并执行
- 按规则响应事件
- 推进自身内生工艺过程
- 对外报告执行结果和状态变化

### 4.3 允许具备

- `attributes`
- `variables`
- `state`
- `services`
- 硬约束 `rules`
- 内生过程触发
- 设备级事件
- 告警
- 审计

### 4.4 不应承担

- 全局调度决策
- 多目标权衡
- 跨对象资源协调
- 开放式推理

### 4.5 一句话定义

**`thing` 是可控的现场执行单元。**

## 5. role 的职责边界

### 5.1 定义

`role` 代表调度员、工艺员、班长、操作员等业务角色的主动决策主体。

### 5.2 职责

- 感知 world 中多个对象的状态
- 理解和使用 `concept`
- 做任务分配、冲突消解、优先级判断
- 调用工具
- 向 `thing` 下达命令
- 跟踪命令执行闭环
- 在异常情况下重规划

### 5.3 允许具备

- goals
- memory
- plans
- tool use
- LLM reasoning
- command authority
- execution tracking
- explanation / rationale

### 5.4 不应承担

- 伪装成物理设备状态机
- 直接绕过 `thing.services` 修改设备内部状态
- 承担低层时序控制

### 5.5 一句话定义

**`role` 是世界里的控制与认知主体。**

## 6. concept 的职责边界

### 6.1 定义

`concept` 是对业务对象的抽象，例如：

- `ProductionOrder`
- `CastingPlan`
- `Heat`
- `TransportTask`

### 6.2 职责

- 承载业务语义
- 作为 `thing` 与 `role` 之间的共享上下文
- 表达业务生命周期和业务状态
- 记录对象之间的业务关系

### 6.3 核心判断

`concept` 应被定义为**被动的业务对象**，不是主动执行者，不应该演化为第三种 runtime 范式。

### 6.4 允许具备

- 标识
- 属性
- `status`
- 生命周期
- `links`
- 审计历史
- ownership metadata

### 6.5 不应承担

- 自主决策
- 自主调度未来事件
- 工具调用
- 主动下命令
- 复杂 behavior runtime

### 6.6 一句话定义

**`concept` 是共享业务事实，不是主动执行者。**

## 7. 三类对象之间的关系

推荐关系链如下：

1. `role` 读取 `concept` 和 `thing`
2. `role` 基于上下文向 `thing` 发命令
3. `thing` 执行后更新自身状态，并反馈事件
4. `role` 根据反馈更新 `concept`
5. `concept` 作为后续协同和决策的业务上下文

换句话说：

- `thing` 管“做没做、能不能做”
- `role` 管“为什么做、现在该做什么”
- `concept` 管“这是哪件业务、做到什么阶段了”

## 8. 状态语义必须分开

这是一个必须明确的硬约束：

- `thing.state`：物理/运行态
- `role`：更偏 `goal / task / decision context`
- `concept.status`：业务态/流程态

不要为了“统一”而把这三者压成一种通用 `state/status` 机制。

## 9. 权限与控制边界

如果 `role` 最终目标是“直接下命令并闭环执行”，则必须明确以下约束：

1. `role` 不能直接改 `thing.variables` 或 `thing.state`
2. `role` 只能通过 `thing.services` 影响设备
3. `thing` 不应随意直接改 `concept`
4. `concept` 由 `role` 或系统流程显式维护

这保证了闭环的控制路径是清楚的：

- `role` 决策
- `service` 执行
- `thing` 反馈
- `role` 更新业务语义

## 10. 三类模型的最小字段集合

### 10.1 thing model

最小必需字段：

- `metadata`
- `attributes`
- `variables`
- `state`
- `services`
- `rules`
- `events`
- `process`
- `alarms`
- `links`

原则上不该有：

- LLM prompt
- tool catalog
- open-ended planning
- 多目标决策策略
- 自由写脚本式全局协调逻辑

一句话：

**`thing` 的核心是“可观测、可命令、可约束、可推进”。**

### 10.2 role model

最小必需字段：

- `metadata`
- `responsibilityScope`
- `goals`
- `contextSources`
- `tools`
- `commands`
- `policies`
- `memory`
- `plans`
- `permissions`

原则上不该有：

- 直接物理变量
- 设备级细粒度状态机
- 绕过 service 直接改设备内部状态的能力
- 设备内生过程定义

一句话：

**`role` 的核心是“看全局、做判断、发命令、盯闭环”。**

### 10.3 concept model

最小必需字段：

- `metadata`
- `properties`
- `status`
- `links`
- `ownership`
- `audit`

可选但要克制的字段：

- `constraints`
- `references`

原则上不该有：

- `services`
- `tools`
- 自主 trigger runtime
- 自主计划
- 自主未来事件调度
- 直接控制 `thing` 的能力

一句话：

**`concept` 的核心是“被引用、被更新、被流转”。**

## 11. 推荐的 schema 收敛方向

不建议继续追求一个“所有对象同构”的超级统一 schema。

更稳妥的方向是：

1. 抽一层 `base object schema`
   只放：
   - `metadata`
   - `identifiers`
   - `links`
   - `audit`

2. 在其上分出三类专用 schema：
   - `thing schema`
   - `role schema`
   - `concept schema`

这样可以共享世界模型和通用能力，但不强行统一主动性和运行时范式。

## 12. 当前阶段最重要的架构判断

这个项目的关键不在于继续细化一个统一 schema，而在于先澄清：

- `thing runtime` 到底负责什么
- `role runtime` 到底负责什么
- `concept` 到底是不是 runtime 主体

当前讨论的结论是：

- `thing` 是主动的执行主体，且应具备一定内生过程能力
- `role` 是主动的决策与指挥主体，负责闭环控制
- `concept` 是被动的业务语义对象，不应成为第三种主动 agent

## 13. 总结

如果用一句话重新定义 Agent Studio：

**这是一个面向工业现场的分层智能体操作系统：`thing` 负责真实可控的现场执行语义，`role` 负责基于全局上下文的决策与指挥，`concept` 负责承载业务语义与生命周期。**

而关于仿真能力，结论也应明确：

**内生过程定义权应回到 `thing`，但未来事件的全局时间调度不应完全私有化到每个 agent 内部。**
