# Agent Studio 技术设计文档

## 1. 文档范围

本文档定义 Agent Studio 的技术定位、核心抽象、运行架构、对象模型、状态事件机制、仿真推演机制、外部服务协同方式，以及 Role Agent 的决策闭环边界。

本文档用于指导后续产品设计、技术架构设计、运行时设计、智能体设计和算法协同设计。本文档不是最终数据库 Schema，也不是详细功能清单。

本文档重点约束以下问题：

1. Agent Studio 的平台定位和边界；
2. `thing`、`role`、`concept` 三类对象的职责边界；
3. `Service`、`Behavior`、`Process`、`Rule`、`State`、`Event` 的语义定义；
4. 本体模型与 Runtime 的关系；
5. Runtime 如何保证权限、规则、资源、时间和状态一致性；
6. 平台如何支持在线映射、离线仿真、预测推演和闭环执行；
7. 外部服务、Role Agent 与平台之间的协同方式；
8. Agent Studio 如何避免退化为通用 Agent 托管平台、流程编排平台或单纯仿真平台。

## 2. 平台定位与边界

Agent Studio 是面向工业现场的本体化推演运行平台。

Agent Studio 的本体模型定义了工业现场的结构化语义：现场有哪些对象，对象对外暴露哪些能力，对象在事件、状态和规则驱动下如何响应，多个对象如何围绕业务目标协同，以及哪些规则约束执行边界。Runtime 加载这套本体模型，在真实现场或仿真环境中驱动对象运行，保证状态、权限、规则和资源的一致性。

本体模型表达以下内容：

- 现场中有哪些对象
- 对象对外暴露哪些能力
- 对象在事件、状态和规则驱动下如何响应
- 多个对象如何围绕业务目标协同
- 哪些规则约束能力、行为和流程
- 哪些事件记录已经发生的事实
- 当前状态如何由事件投影
- 外部服务基于哪些上下文计算
- Role Agent 如何形成决策
- 决策如何在 Runtime 约束下执行和回写

Agent Studio 的核心职责是维护一套统一、可运行、可推演、可审计、可接入真实现场的工业本体模型，并通过 Runtime 将模型约束落实到状态更新、流程推进、算法调用和执行闭环中。

Agent Studio 不承担以下职责：

- 不作为通用 Agent 托管平台
- 不作为单纯工业仿真平台
- 不作为传统 BPM 或流程编排平台
- 不作为算法训练或算法管理平台本身
- 不作为 PLC、SCADA、MES、L2 点位采集平台
- 不允许 Role Agent 或外部服务绕过 Runtime 直接控制现场对象

## 3. 总体技术架构

Agent Studio 的技术架构分为三层：

- 语义定义层
- 运行编排层
- 状态事件层

### 3.1 语义定义层

语义定义层定义 Runtime 可理解和执行的结构化语义对象。

主要实体包括：

- Object
- Service
- Behavior
- Process
- Rule
- 外部服务
- Permission Policy
- Event Schema
- State Projection

该层回答以下问题：

- 有哪些对象
- 对象对外暴露哪些 Service
- 对象在什么事件、状态和规则下触发 Behavior
- 哪些 Process 可以启动
- 哪些 Rule 约束 Service、Behavior 和 Process
- 外部服务需要哪些上下文
- 状态如何由事件投影

### 3.2 运行编排层

运行编排层负责接收执行意图、校验规则、调度资源、推进流程和调用模型。

主要实体包括：

- Command
- Service Invocation
- Behavior Trigger
- Process Instance
- Activity
- Resource Lock
- Runtime Context
- Event Scheduler
- Simulation Scheduler
- 外部服务调用
- Audit Context

该层回答以下问题：

- 谁发起调用
- 是否具备权限
- 当前状态是否允许执行
- 需要占用哪些资源
- 需要调用哪个 Service、Behavior、Process 或外部服务
- 执行结果如何记录和审计

### 3.3 状态事件层

状态事件层负责保存事实、投影状态、支持回放、审计和仿真分支。

主要实体包括：

- Event Store
- State Store
- State Projection
- Current World Snapshot
- Branch World Snapshot
- Execution Record
- Model Execution Record
- Audit Log
- Simulation Trace

该层回答以下问题：

- 发生过什么事件
- 当前状态是什么
- 状态由哪些事件投影而来
- 哪些执行可以回放、复盘和审计
- 哪些分支世界用于未来推演

## 4. 设计时与运行时

Agent Studio 必须区分设计时和运行时。

### 4.1 设计时

设计时用于定义工业现场如何被结构化表达。

设计时对象包括：

- Object
- Service
- Behavior
- Process
- Rule
- Event Schema
- State Projection
- 外部服务
- Role Agent Scope
- Permission Policy
- 现场数据映射关系
- 仿真参数
- 运行边界

设计时回答以下问题：

- 哪些对象存在
- 对象具备哪些能力
- 对象在什么条件下响应
- 对象之间如何协同
- 哪些规则限制执行
- 哪些事件被记录
- 状态如何变化
- 哪些外部服务可被调用
- 哪些 Role Agent 有权发起决策

### 4.2 运行时

运行时加载本体模型，在真实现场或仿真环境中驱动对象运行。

Runtime 负责：

- 接入真实事件
- 更新对象变量
- 投影对象状态
- 启动流程实例
- 校验权限、规则和资源
- 占用和释放资源
- 调用外部服务
- 驱动 Role Agent 决策
- 调度真实事件和仿真事件
- 管理 Current World 和 Branch World
- 执行 Service 和 Process
- 记录事件、执行记录和审计记录

运行时必须严格遵循设计时定义。运行时不得脱离设计时定义随意产生新的业务语义，设计时变更也不得无追溯地改变既有运行记录和审计记录。

## 5. 核心对象模型

Agent Studio 不应将所有对象统一抽象为 Agent。平台对象分为三类：

```text
Object
  ├── thing
  ├── role
  └── concept
```

三类对象共享同一套关系网络、事件体系、规则体系和审计机制，但不共享同一种主动性。

### 5.1 thing

`thing` 表示物理世界或现场逻辑世界中的执行对象。

典型对象包括：

- 转炉
- 连铸机
- 天车
- 钢包
- 铁包
- 废钢斗
- 加热炉
- 轧机
- 库位
- 运输轨道
- 能源介质管网
- 质量检测设备

`thing` 的职责包括：

- 表达静态属性和动态变量
- 表达运行状态
- 通过 transitions 定义合法的状态转换路径
- 暴露可调用 Service
- 根据 Behavior 响应事件和状态变化
- 接收 Runtime 或 Process 调度
- 校验自身约束
- 执行动作
- 产生事件和告警
- 支持审计和追溯

`thing` 的状态机（transitions）是其内生行为的骨架。 transitions 定义了在当前状态下，接收到什么事件、满足什么规则时，可以迁移到什么目标状态。Behavior 的响应通常是触发一次状态迁移，而一段 transitions 的串联构成了 thing 的内生 Process。

`thing` 不应承担以下职责：

- 全局调度决策
- 多目标权衡
- 跨对象资源协调
- 开放式业务推理
- 绕过 Service 修改状态
- 直接修改业务对象状态

### 5.2 role

`role` 表示调度员、工艺员、班长、操作员、能源调度员、质量工程师等业务角色的智能体。

`role` 是认知、决策和指挥主体，可由 LLM、规则、外部服务、历史经验和人工确认机制共同驱动。

`role` 的职责包括：

- 观察多个 thing 的状态
- 理解多个 concept 的业务语义
- 感知流程进展
- 识别异常和风险
- 调用外部服务
- 发起 Service 调用
- 启动或调整 Process
- 进行任务分配、冲突消解和优先级判断
- 跟踪执行闭环
- 在异常情况下重规划
- 解释决策依据

`role` 不应承担以下职责：

- 伪装成设备状态机
- 直接修改 `thing.state` 或 `thing.variables`
- 绕过 thing.Service 执行底层动作
- 承担设备内部内生过程定义
- 绕过 Runtime 控制现场对象
- 绕过规则和权限修改业务状态

### 5.3 concept

`concept` 表示业务语义对象，不是物理执行对象，也不是主动决策主体。

典型对象包括：

- ProductionOrder
- Heat
- CastingPlan
- TransportTask
- ScheduleTask
- MaterialLot
- QualityDecision
- EnergyPlan

`concept` 的职责包括：

- 承载业务语义
- 表达业务生命周期
- 表达业务状态
- 连接多个 thing
- 作为 Role Agent 决策上下文
- 作为 Process 执行目标
- 记录业务关系和业务历史
- 支撑审计和追溯

`concept` 不应自主决策、自主调用工具、自主调度未来事件、主动下命令或直接控制 `thing`。

### 5.4 对象协作关系

三类对象的协作链路如下：

Role Agent 观察 thing 和 concept
  → Role Agent 发起 Service 调用或 Process 执行
    → Runtime 校验权限、规则和资源
      → Process 组织一个或多个 thing 协同执行
        → thing 执行 Service 或触发 Behavior
          → Event 记录事实
            → State Projection 更新状态
              → concept 显式更新业务状态
                → Role Agent 跟踪反馈并必要时重规划

## 6. 能力、行为、流程与规则

### 6.1 Service

`Service` 表示对象对外暴露的可调用能力。

Service 回答的问题是：

- 对象对外暴露了什么能力
- 外部在什么条件下可以调用
- 调用后应产生哪些事件
- 调用结果如何影响状态投影

`thing` 的 Service 示例：

| 对象 | Service 示例 |
| --- | --- |
| 转炉 | 接收铁水、接收废钢、吹炼、出钢 |
| 天车 | 吊运钢包、吊运铁包、吊运废钢斗 |
| 钢包 | 接收钢水、承载钢水、等待精炼 |
| 连铸机 | 开浇、停浇、换包 |
| 加热炉 | 装炉、出炉、加热 |
| 轧机 | 开轧、停轧、换辊、切换规格 |

`role` 的 Service 可以表现为其可发起的指挥能力，例如下达任务、调整顺序、触发重排、处理异常和确认执行结果。

Service 调用必须经过 Runtime：

调用意图
  → 权限校验
    → 规则校验
      → 资源校验
        → 执行动作
          → 产生事件
            → 更新状态投影
              → 记录审计

### 6.2 Behavior

`Behavior` 表示对象在特定事件、状态或规则条件下的内生响应机制。

Behavior 回答的问题是：

- 当接收到某类事件时，对象如何响应
- 当状态满足某个条件时，对象如何自我推进
- 当规则被触发时，应调用哪个 Service 或 Function
- 状态变化后是否需要产生新的事件
- 是否需要启动、暂停、取消或调整 Process

Service 与 Behavior 的边界如下：

| 概念 | 语义重点 | 触发方式 |
| --- | --- | --- |
| Service | 对外暴露的可调用能力 | 由 Role Agent、Process、Runtime、外部系统或规则调用 |
| Behavior | 事件、状态和规则驱动的自我响应 | 由 Event、State、Rule 或 Scheduler 触发 |

示例：

当接收到 ScrapArrived 事件时：
  → 校验废钢斗是否到位
    → 调用 Converter.receiveScrap Service
      → 改变 Converter 和 Heat 的状态
        → 产生 ScrapChargingStarted 事件

在该示例中，`Converter.receiveScrap` 是 Service；”接收到 ScrapArrived 后触发接收废钢并改变状态”是 Behavior。

Behavior 的典型响应是触发一次状态迁移（transition）。当 Behavior 被触发时，Runtime 校验当前状态是否满足 transition 的 `from` 条件，满足后执行相应动作并进入 `to` 状态。多个 transitions 按事件和规则串联，构成 thing 的内生状态机。

### 6.3 Process

`Process` 表示一个或多个对象围绕业务目标展开的一段可执行过程。

Process 定义以下内容：

- 参与对象
- 业务目标
- 前置条件
- Service 调用顺序
- Behavior 触发关系
- 资源占用和释放
- 事件输出
- 状态投影
- 异常处理

Process 不应被理解为传统固定流程图。Process 是对象能力、行为、规则和事件之间的运行组织方式。

示例：

- “转炉接收废钢”是转炉 Service
- “天车吊运废钢斗”是天车 Service
- “废钢斗倾倒废钢”是废钢斗 Service
- “兑废钢流程”是多个 Service 在规则和资源约束下的协同组织

#### Process 生命周期

Process Instance 具有明确的生命周期状态：

- `Created`：Process 被创建，等待前置条件满足
- `Running`：前置条件满足，Process 开始执行
- `Waiting`：等待外部事件（如设备到位、人工确认、资源释放）
- `Suspended`：因异常或规则触发而暂停，等待 Role Agent 或系统决策
- `Resumed`：异常解除或决策完成后恢复
- `Completed`：所有步骤执行完毕，业务目标达成
- `Cancelled`：因规则冲突、资源不足或 Role Agent 主动取消而终止

状态转换由 Event 驱动或由 Rule 触发：

- `ScrapArrived` 事件触发 → `Created` → `Running`
- `CraneConflict` 规则触发 → `Running` → `Suspended`
- Role Agent 决策 → `Suspended` → `Resumed`
- `ConverterNotReady` 规则触发 → `Running` → `Cancelled`

#### Process 与核心概念的协同

Process 不是孤立执行的，它与平台核心概念形成以下协同关系：

**Process ↔ Service**
Process 编排一个或多个 Service 的调用，但 Service 本身不感知 Process。Process Instance 维护调用上下文，将前一步的输出作为后一步的输入。

**Process ↔ Behavior**
Service 调用可能触发 Behavior，Behavior 产生的新 Event 可能推进 Process 到下一步。例如：调用 `Converter.receiveScrap` Service 触发 Behavior，Behavior 产生 `ScrapChargingStarted` Event，Event 驱动 Process 进入下一步。

**Process ↔ Rule**
Rule 在 Process 的三个阶段生效：
- **启动前**：校验前置条件（资源可用、状态允许、安全边界）
- **步骤间**：校验步骤转换条件（权限、时序、资源占用）
- **异常时**：触发补偿、暂停或取消

**Process ↔ Event**
Process 的推进由 Event 驱动。每一步完成后产生 Event，Event 被 Event Bus 分发，可能直接推进 Process 到下一步，或触发 Behavior 再产生新 Event，或被 Role Agent 消费后决策推进。

**Process ↔ Role Agent**
Role Agent 可以启动 Process、在 `Waiting` 时提供决策输入、在 `Suspended` 时决定恢复/重排/取消，以及在 Branch World 中预演不同 Process 方案。

#### Process 的运行推进方式

Process 的推进不是简单的顺序执行，而是**事件驱动的状态转换**：

Event 到达 → Rule 校验当前步骤约束 → 通过则调用 Service / 触发 Behavior → 产生新 Event → 更新 State Projection → Process 状态推进 → Rule 校验下一步约束 → 循环

这种推进方式使得 Process 可以响应异步事件、在规则约束下灵活调整、在异常时暂停并等待干预、在 Branch World 中复制和推演。

#### Process 的异常处理

Process 的异常处理不是简单的回滚，而是**状态驱动的干预机制**：

| 异常类型 | 处理方式 | 示例 |
|---------|---------|------|
| 资源冲突 | `Suspended` → Role Agent 重排资源 | 天车冲突，调度员重新分配 |
| 前置条件不满足 | `Waiting` → 等待条件满足或超时取消 | 废钢斗未到位，等待 10 分钟后取消 |
| 规则违反 | `Suspended` → 人工确认或自动补偿 | 温度超限，触发降温 Behavior |
| 设备故障 | `Suspended` → Role Agent 决策转产或等待修复 | 连铸机故障，决策是否改浇次 |

Process 分为两类：

- 内生流程：单个 thing 内部根据自身规则推进的过程，由其状态机（transitions）驱动。一段 transitions 的串联构成一个完整的内生 Process，如 `idle → charging → blowing → tapping → idle`
- 协同流程：多个 thing、role、concept 围绕业务目标协同推进的过程

### 6.4 Rule

`Rule` 表示 Service、Behavior、Process、State Projection 和 Role Agent 决策的约束条件。

Rule 是一等语义对象，不应只是流程或 Service 的附属配置。

Rule 可挂载于：

- Object
- Service
- Behavior
- Process
- State Projection
- 外部服务
- Role Agent Policy
- Runtime Execution

Rule 的作用包括：

- 权限校验
- 状态校验
- 资源校验
- 安全边界校验
- 流程前置条件校验
- 异常触发
- 人工确认要求
- 仿真方案过滤

## 7. 状态与事件

### 7.1 State

`State` 表示对象、流程或业务在当前时刻的状态投影。

State 不是事实本身。事实由 Event 记录，State 是 Event 经过 State Projection 后形成的结果。

State 示例：

- Converter.state = Blowing
- Crane.state = Busy
- Heat.status = Tapping
- CastingPlan.status = AtRisk
- TransportTask.status = Waiting

State 必须满足以下约束：

- 关键状态变化必须有事件来源
- 状态投影逻辑必须可追溯
- Role Agent 和外部服务不得绕过 Runtime 直接修改状态
- 在线状态和仿真状态必须隔离

### 7.2 Event

`Event` 表示已经发生的事实记录。

Event 用于：

- 驱动 Behavior
- 推进 Process
- 投影 State
- 触发 Rule
- 支持回放
- 支撑仿真
- 形成审计依据

Event 不是日志。日志记录系统运行情况，Event 记录模型运行中的业务事实。

事件来源包括：

- 真实现场事件
- 人工确认事件
- Runtime 执行事件
- Process 推进事件
- 外部服务调用事件
- Role Agent 决策事件
- 仿真事件
- 预测事件

## 8. Runtime 执行模型

Runtime 是加载并运行本体模型的核心组件。

Runtime 职责包括：

- 接收 Role Agent、系统规则或外部系统发起的调用
- 校验权限
- 校验对象状态
- 校验流程前置条件
- 占用和释放资源
- 推进 Process Instance
- 触发 Behavior
- 调度未来事件
- 消费 Event 并更新 State
- 同步真实现场状态
- 管理仿真时间
- 管理 Current World 和 Branch World
- 调用外部服务
- 记录审计日志
- 在异常情况下取消、暂停或重排流程

Runtime 的控制路径如下：

Role Agent 决策
  → 调用外部服务
    → 形成建议或方案
      → 调用 Service 或 Process
        → Runtime 校验权限、规则和资源
          → thing 执行能力或触发 Behavior
            → Event 记录事实
              → State Projection 更新状态
                → Role Agent 跟踪闭环

Runtime 必须满足以下硬边界：

- Role Agent 不能直接修改 `thing.variables` 或 `thing.state`
- Role Agent 只能通过 Service 或 Process 影响现场对象
- thing 不应随意修改 concept.status
- concept.status 应由流程运行、Role Agent 确认或系统规则显式维护
- 跨对象动作不应由单个 thing 私有发起
- 涉及资源占用、位置约束、业务许可的动作应通过 Process 执行
- 外部服务不能直接控制现场对象
- 所有关键状态变化必须有事件和审计记录支撑

## 9. 运行模式与推演机制

Agent Studio 支持同一套本体模型在多种模式下运行：

| 模式 | 输入来源 | 目标 |
| --- | --- | --- |
| 离线仿真模式 | 人工配置、历史数据、模拟事件 | 验证对象、流程、规则和调度策略 |
| 在线映射模式 | 传感器、PLC、SCADA、MES、L2 等现场数据 | 实时映射现场状态，形成在线本体模型 |
| 预测推演模式 | Current World + 假设动作 | 推演未来状态并比较候选方案 |
| 闭环执行模式 | Role Agent + Runtime + Service / Process | 在权限和安全边界内触发执行并跟踪反馈 |

### 9.1 Current World

`Current World` 表示由真实事件和真实状态驱动的当前现场。

示例：

- 1#转炉正在吹炼
- 3#天车正在吊运钢包
- Heat#001 处于吹炼中
- 2#精炼炉预计 12 分钟后空闲

Current World 必须以真实事件为准。

### 9.2 Branch World

`Branch World` 表示从 Current World 复制出的状态快照，用于未来推演。

Branch World 用于回答：

- 如果优先 1#转炉出钢，未来可能怎样
- 如果优先处理 2#转炉异常，未来可能怎样
- 如果调整 3#天车任务顺序，未来可能怎样

Branch World 可比较以下指标：

- 连铸等待时间
- 转炉等待时间
- 天车冲突次数
- 钢包周转时间
- 温降风险
- 计划偏离量
- 能源消耗
- 质量风险

仿真时间轴必须由 Simulation Scheduler 或全局 Runtime 统一调度，不应由每个 `thing` 私有控制。

## 10. 外部服务（External Service）

Agent Studio 不替代外部专业能力。外部团队开发的算法、工具和数据处理逻辑，在平台中注册为**外部服务**（External Service），供 Role Agent 调用。Agent Studio 负责为外部服务提供语义上下文、执行边界、仿真环境和闭环机制。

平台与外部服务分工如下：

| 角色 | 职责 |
| --- | --- |
| Agent Studio | 描述本体模型、维护状态、组织流程、约束执行、记录事件 |
| 外部服务 | 提供专业计算和查询：预测、优化、匹配、排序、诊断、评估、查询 |
| Role Agent | 理解目标、选择服务、组织决策、解释结果、发起执行 |
| Runtime | 校验权限、规则、资源，推进流程并记录闭环 |

外部服务分为两类：

| 类型 | 作用 | 示例 |
| --- | --- | --- |
| 算法服务 | 产生预测、判断或方案 | 排程优化、路径规划、质量预测、能源预测 |
| 工具服务 | 查询或辅助处理 | 查库存、查计划、查历史事件、计算指标 |

外部服务与 Role Agent 的 tools：

Role Agent 由 LLM 驱动时，外部服务以 **tools** 的形式被调用。外部服务在注册时需提供 tool description，包括名称、功能说明、输入参数 schema 和输出 schema，供 LLM 理解服务用途并决定何时调用。

外部服务与对象 Service 的区别：

- 外部服务由外部系统开发，在平台中注册后供 Role Agent 调用，输出计算结果但不直接改变状态
- 对象 Service 是 `thing` / `role` / `concept` 自身定义的能力，由 Runtime 直接调度执行（见 §6.1）

外部服务输出包括：

- 预测结果
- 评分结果
- 推荐方案
- 排序结果
- 风险判断
- 约束冲突
- 候选动作
- 方案评价

外部服务不得直接改变 State，也不得直接控制现场对象。其输出只能作为 Role Agent 和 Runtime 的决策输入。

Agent Studio 为外部服务提供以下运行支撑：

- 统一 world snapshot 输入
- 对象状态、流程状态和业务状态
- 资源可用性
- 事件历史
- 规则和约束
- 候选动作空间
- Branch World 仿真评估环境
- 执行闭环记录
- 服务调用审计和复盘数据

## 11. Role Agent 决策闭环

Role Agent 是基于 Runtime 提供的状态、事件和服务，结合本体模型定义的约束和外部服务的计算结果，完成业务决策的智能角色。

Role Agent 不替代外部服务，不直接控制现场设备，也不绕过 Runtime。

推荐推理分级如下：

| 类型 | 承担者 | 示例 |
| --- | --- | --- |
| 确定性规则校验 | Runtime / Rule Engine | 钢包未到位不能出钢 |
| 复杂数值计算 | 外部服务 | 天车路径优化、温降预测 |
| 语义理解与意图识别 | Role Agent / LLM | 将“连铸不能断”识别为节奏保持目标 |
| 多方案组织与解释 | Role Agent | 比较多个算法候选方案并解释原因 |
| 最终执行校验 | Runtime | 权限、资源、状态、安全边界检查 |

硬边界如下：

- LLM 不直接控制现场
- 外部服务不直接修改状态
- Role Agent 不绕过 Runtime
- Runtime 不绕过规则
- thing 不承担全局决策
- concept 不主动执行

典型决策闭环如下：

Role Agent 观察 Current World
  → 识别业务目标、异常或风险
    → 调用外部服务
      → 组织候选方案
        → 在 Branch World 中推演
          → 比较方案效果
            → 形成建议或决策
              → 人工确认或自动触发 Process
                → Runtime 校验并执行
                  → Event 和 State 形成反馈
                    → Role Agent 跟踪闭环并必要时重规划

## 12. Schema 收敛方向

不建议设计一个所有对象完全同构的超级 Schema。推荐采用 Base Object + 分类 Schema + 运行模型的结构。

### 12.1 Base Object Schema

Base Object 只包含所有对象共有字段：

- metadata
- identifiers
- name
- type
- description
- tags
- links
- audit

### 12.2 thing schema

建议字段：

- metadata
- attributes
- variables
- state
- transitions
- services
- behaviors
- rules
- processes
- events
- alarms
- links
- audit

不应包含：

- LLM prompt
- 开放式规划策略
- 全局调度策略
- 多目标决策逻辑
- 绕过 Service 的状态修改脚本

### 12.3 role schema

建议字段：

- metadata
- responsibilityScope
- goals
- contextSources
- tools
- modelServices
- services
- policies
- memory
- plans
- permissions
- audit

不应包含：

- 设备级细粒度状态机
- 直接物理变量
- 设备内生过程定义
- 直接修改 `thing.state` 的能力
- 绕过 Runtime 的现场控制能力

### 12.4 concept schema

建议字段：

- metadata
- properties
- status
- lifecycle
- links
- ownership
- references
- audit

不应包含：

- services
- tools
- 自主触发 Runtime
- 自主计划
- 自主未来事件调度
- 直接控制 thing 的能力

### 12.5 外部服务的 tool description schema

外部服务注册时需提供 tool description，供 LLM 理解服务用途、选择调用并解析返回结果。建议字段：

```yaml
metadata
serviceType        # algorithm / tool
description        # 供 LLM 理解的功能说明
inputSchema        # 参数 schema，供 LLM 生成调用参数
outputSchema       # 返回值 schema，供 LLM 解析结果
requiredContext    # 调用前需提供的上下文
constraints        # 调用约束（如权限、资源、前置状态）
version
owner
executionMode      # sync / async
timeout
confidenceOutput   # 是否输出置信度
explainability     # 是否提供可解释性输出
audit
```

外部服务输出不得直接改变 State，只能作为 Role Agent 和 Runtime 的决策输入。

## 13. 钢铁场景参考链路

以炼钢调度员 Role Agent 为例。

### 13.1 可观察上下文

Role Agent 可观察：

- 转炉状态
- 天车位置
- 钢包状态
- 铁包状态
- 废钢斗状态
- 精炼炉状态
- 连铸机节奏
- 炉次状态
- 浇次计划
- 当前异常事件
- 未来预测风险

### 13.2 可调用模型

Role Agent 可调用：

- 出钢时间预测模型
- 连铸节奏预测模型
- 天车冲突检测模型
- 钢包周转优化模型
- 温降预测模型
- 炉次排序优化模型

### 13.3 决策过程

典型过程：

观察 Current World
  → 发现 20 分钟后可能连铸断浇
    → 调用连铸节奏预测模型
      → 调用钢包周转优化模型
        → 调用天车冲突检测模型
          → 生成多个候选方案
            → 在 Branch World 中推演
              → 比较方案效果
                → 给出建议
                  → 人工确认或自动触发流程
                    → 跟踪执行反馈

### 13.4 输出与审计

Role Agent 可输出：

- 建议将 3#天车优先分配给 1#转炉钢包
- 建议延后 2#转炉出钢 3 分钟
- 该方案预计可降低连铸等待风险
- 该方案不会引发新的天车路径冲突
- 需调度员确认后执行

Runtime 记录：

- 建议来源
- 调用模型
- 输入状态
- 输出方案
- 人工确认
- 实际执行事件
- 最终效果

### 13.5 典型 Process 示例：兑废钢流程

"兑废钢"是转炉冶炼前将废钢从废钢斗倒入转炉的协同流程。它涉及转炉、天车、废钢斗三个 thing，由 Role Agent（调度员）发起，在 Runtime 约束下执行。

#### 参与对象与目标

- **转炉（Converter）**：接收废钢，目标状态为"等待吹炼"
- **天车（Crane）**：吊运废钢斗，目标为完成吊运并释放
- **废钢斗（ScrapBucket）**：承载废钢并完成倾倒
- **炉次（Heat，concept）**：跟踪废钢装入量，更新业务状态

#### 流程步骤与事件驱动

1. **启动**：Role Agent 发起"兑废钢"Process
   - Runtime 校验前置条件：转炉状态为 `Waiting`，天车可用，废钢斗在位
   - Rule 校验：废钢量 ≤ 转炉容量，天车载重 ≥ 废钢斗重量

2. **天车吊运**：调用 `Crane.transport(ScrapBucket, Converter)` Service
   - 天车状态变为 `Busy`，占用天车资源
   - 产生 `CraneTransportStarted` Event

3. **到位等待**：天车到达转炉上方
   - 产生 `CraneArrived` Event
   - Process 进入 `Waiting`，等待倾倒信号

4. **废钢倾倒**：调用 `ScrapBucket.dump(Converter)` Service
   - 触发 Behavior：校验转炉口是否对准、炉内温度是否安全
   - 产生 `ScrapDumpingStarted` Event

5. **装入确认**：废钢倾倒完成
   - 产生 `ScrapLoaded` Event
   - Heat 更新废钢装入量，状态变为 `ScrapCharged`

6. **天车释放**：调用 `Crane.release()` Service
   - 天车状态变为 `Idle`，释放资源
   - 产生 `CraneReleased` Event

7. **完成**：Process 状态变为 `Completed`
   - 转炉状态变为 `ReadyForBlowing`
   - Runtime 记录执行审计

#### 规则与异常处理

| 阶段 | Rule | 触发动作 |
|------|------|---------|
| 启动前 | 废钢斗重量 > 天车载重 | 拒绝启动，告警 |
| 吊运中 | CraneConflict（天车路径冲突）| Process `Suspended`，Role Agent 重排 |
| 倾倒前 | 转炉口未对准 | `Waiting`，等待人工确认或自动调整 |
| 倾倒中 | 炉内温度 > 安全阈值 | 触发 `Cooling` Behavior，暂停倾倒 |
| 完成后 | 废钢量 < 最小装入量 | Process `Completed` 但标记异常，Role Agent 决策补装 |

#### Role Agent 干预点

- **启动前**：确认废钢种类和配比是否符合工艺要求
- **`Suspended` 时**：天车冲突时决策优先处理哪一炉
- **完成后**：确认装入量，决定是否需要补装或调整吹炼参数

#### Branch World 推演价值

同一套"兑废钢"Process 可在 Branch World 中推演不同方案：

- 如果优先使用 3#天车而非 2#天车，吊运时间减少 2 分钟，但可能影响后续铁包吊运
- 如果等待 2#转炉空闲后再同时给 1#、2#转炉兑废钢，可以减少天车空驶，但增加 1#转炉等待时间

Runtime 在 Branch World 中复制当前 Process，替换参数后推演，输出对比指标供 Role Agent 决策。

## 14. 可信度与评测

Agent Studio 必须评估 Role Agent 的决策依据、采纳情况、执行效果、模型偏差和闭环质量。

建议指标包括：

- 建议采纳率
- 人工修改率
- 执行成功率
- 规则冲突率
- 仿真预测偏差
- 外部服务误差
- Role Agent 解释一致性
- 事件识别准确率
- 状态投影准确率
- Branch World 推演命中率
- 模型调用成功率
- 决策闭环完成率
- 异常处理有效率

这些指标用于支撑：

- 模型治理
- 算法优化
- 调度策略复盘
- 智能体能力评估
- 现场运行可信度提升

## 15. 总结

Agent Studio 是面向工业现场的本体化推演运行平台。

平台以 `thing`、`role`、`concept` 三类对象为基础，以 `Service` 表达对象对外可调用能力，以 `Behavior` 表达事件和规则驱动的内生响应机制，以 `Process` 组织对象协同，以 `Rule` 约束执行边界，以 `State` 表达当前结果，以 `Event` 记录模型运行事实，以外部服务支撑专业决策，以 `Runtime` 保证时间、资源、状态和执行闭环的一致性。

最终运行关系如下：

- 真实事件驱动 Current World
- 仿真机制推演 Branch World
- 外部服务提供专业计算
- Role Agent 组织决策闭环
- Runtime 保证所有执行在规则、权限和审计约束下运行
