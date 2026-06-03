# Agent Studio 工业本体化世界模型运行平台设计文档

## 1. 文档目的

本文档用于系统梳理 Agent Studio 的产品定位、核心抽象、模型边界、运行机制、现场接入方式、仿真推演能力、算法模型协同方式，以及 role agent 的决策闭环机制。

本文档不是最终数据库 Schema，也不是详细功能清单，而是 Agent Studio 后续产品设计、技术架构设计、运行时设计、智能体设计和算法协同设计的基础性约束文档。

本文档重点回答以下问题：

1. Agent Studio 到底是什么，不是什么；
2. Agent Studio 的核心抽象应如何收敛；
3. 如何理解工业世界模型与本体模型之间的关系；
4. `thing`、`role`、`concept` 三类对象的边界是什么；
5. `service`、`process`、`rule`、`state`、`event` 应如何定义；
6. 平台如何同时支持离线仿真、在线映射和预测推演；
7. 算法模型与平台之间是什么关系；
8. role agent 如何组织决策和执行闭环；
9. runtime 如何保证权限、规则、资源、时间和状态一致性；
10. Agent Studio 如何避免变成概念复杂、边界混乱的通用 Agent 平台。

---

## 2. 项目定位

Agent Studio 不应被简单定义为一个“通用 Agent 托管平台”，也不应被限定为一个“工业仿真平台”。

更准确的定位是：

> **Agent Studio 是一个面向工业现场的本体化世界模型运行平台。**

这里的“世界模型”，不是普通的数据模型，也不是简单的数字孪生模型，而是对工业现场中的对象、能力、流程、规则、状态、事件、算法和智能体决策过程的统一语义表达。

这里的“本体化”，并不意味着产品前台必须暴露“本体论”这个理论概念，而是指平台在底层方法论上要回答几个根本问题：

```text
世界中有什么？
这些对象能做什么？
在什么条件下可以做？
多个对象如何协同完成一件事？
做完之后产生什么事件？
事件如何改变状态？
状态如何被追溯和解释？
算法模型基于什么上下文计算？
role agent 如何形成决策？
决策如何回写到业务系统或现场执行系统？
```

因此，Agent Studio 的核心任务不是“让所有东西都变成 Agent”，而是构建一个统一、可运行、可推理、可接入真实现场、可进行仿真推演、可支撑智能决策闭环的工业世界模型。

一句话概括：

> **Agent Studio 用对象描述工业世界，用能力描述对象能做什么，用流程描述对象如何协同，用规则约束什么可以做，用事件记录已经发生的事实，用状态表达当前世界结果，用算法模型支撑专业计算，用 role agent 组织决策，用 runtime 保证执行闭环。**

---

## 3. Agent Studio 不是什么

为了避免产品边界发散，需要先明确 Agent Studio 不是什么。

Agent Studio 不是单纯的 Agent 托管平台。它不是把多个大模型 Agent 注册进来，然后做工具调用和对话编排。Agent 只是平台中的一种角色对象，不能成为所有对象的统一抽象。

Agent Studio 不是单纯的仿真平台。仿真只是它的一种运行模式。平台既要能离线推演，也要能接入真实现场，形成在线世界模型。

Agent Studio 不是单纯的流程编排平台。流程只是对象能力在特定业务目标下的组合，不应退化为传统 BPM 或工作流系统。

Agent Studio 不是单纯的算法平台。算法模型负责预测、优化、诊断、评分和方案生成，Agent Studio 负责提供语义上下文、执行边界、仿真环境和闭环机制。

Agent Studio 不是单纯的数据采集平台。它不是把 PLC、SCADA、MES、L2 的点位数据采集上来就结束，而是要把低层数据转换成有业务语义的对象状态、事件事实和流程进展。

Agent Studio 不是直接控制现场设备的黑箱智能体系统。任何 role agent 和算法模型都不能绕过 service、process、runtime、规则、权限和安全边界直接修改现场对象状态。

---

## 4. 底层方法论：工业本体化世界模型

Agent Studio 的底层方法论可以称为“工业本体化世界模型”。

传统 IT 系统通常围绕数据库表、业务流程和功能页面构建。数据库表描述数据，流程图描述业务步骤，页面承载人工操作。但这种方式容易带来一个问题：对象、行为、规则、事件和状态之间的语义关系被打散了。

很多业务规则被写进代码里；很多行为逻辑被封装在系统功能里；很多状态变化只表现为字段更新；很多异常处理依赖人工经验；很多分析结论难以回写到执行系统。

Agent Studio 要解决的正是这个问题。

它不只描述工业现场中“有什么对象”，还要描述：

```text
对象能提供什么能力；
能力受哪些规则约束；
流程如何组织多个对象协同；
事件如何记录事实；
状态如何由事件投影而来；
算法模型基于哪些上下文计算；
role agent 如何理解目标并组织决策；
runtime 如何执行、校验、回写和审计。
```

因此，Agent Studio 的世界模型不是静态数据模型，而是一个动态运行模型。

其核心原则可以概括为：

> **对象是世界的基础，能力是对象的行为，规则是行为的边界，流程是能力的编排，事件是发生过的事实，状态是事实作用后的投影，runtime 是世界运行的一致性机制，role agent 是世界中的认知与决策主体。**

---

## 5. 前台简化与后台严谨

Agent Studio 面向工业用户、业务人员、算法人员和研发人员，不能把概念设计得过于复杂。

因此，平台应采用“两层抽象”：

```text
前台概念要少，便于理解、配置和讨论；
后台机制要严，保证运行、推演和闭环的一致性。
```

### 5.1 产品前台概念

产品前台建议只暴露六类核心概念：

```text
对象 Object
能力 Service
流程 Process
规则 Rule
状态 State / Status
事件 Event
```

这六类概念足以支撑绝大多数工业现场建模、运行、仿真和智能决策需求。

| 概念    | 含义                           | 作用                                         |
| ------- | ------------------------------ | -------------------------------------------- |
| Object  | 世界中存在的对象               | 表达设备、角色、任务、订单、炉次、计划等实体 |
| Service | 对象对外暴露的能力             | 表达对象能做什么                             |
| Process | 多个对象围绕业务目标展开的过程 | 表达对象如何协同                             |
| Rule    | 能力和流程执行的约束           | 表达什么条件下可以做                         |
| State   | 对象、流程或业务的当前状态     | 表达当前世界是什么样                         |
| Event   | 已经发生的事实记录             | 用于驱动、追溯、审计、回放、仿真和复盘       |

其中，用户主要配置：

```text
对象
能力
流程
规则
```

系统运行时主要产生和维护：

```text
状态
事件
流程实例
算法调用记录
执行记录
审计记录
仿真记录
状态投影
```

也就是说，用户不应主要围绕“事件”建模，而应围绕“对象、能力、流程、规则”建模；事件是平台运行过程中自动产生和记录的事实。

### 5.2 技术后台机制

后台可以存在更细的技术对象和运行机制，例如：

```text
command
service invocation
process instance
activity
resource lock
event scheduler
simulation scheduler
state projection
model service
runtime context
branch world
event store
audit log
world model version
```

但这些不一定作为用户建模时的一级概念暴露。

例如，“Command”在技术上表示一次执行意图，但产品上可以表现为“调用某个能力”或“启动某个流程”。

“Activity”在技术上表示流程中的一个执行节点，但产品上可以统一归入“流程步骤”。

“State Projection”在技术上表示状态投影机制，但产品上可以表现为“当前状态”。

这种设计原则可以概括为：

> **理论上分清，产品上收敛；前台少概念，后台强约束。**

---

## 6.  设计时与运行时

Agent Studio 应明确区分设计时和运行时。

### 6.1 设计时 Design Time

设计时用于定义工业世界如何被表达。

主要工作包括：

```text
定义 Object
定义 Service
定义 Process
定义 Rule
定义 Event Schema
定义 State Projection
定义 Model Service
定义 Role Agent 的职责、权限和上下文
定义现场数据映射关系
定义仿真参数
定义运行边界
```

设计时回答的是：

```text
这个工业世界应如何被描述？
哪些对象存在？
它们能做什么？
它们之间如何协同？
什么条件下允许执行？
哪些事件会被记录？
状态如何变化？
哪些算法模型可被调用？
哪些 role agent 有权发起决策？
```

### 6.2 运行时 Runtime

运行时用于让工业世界模型真正运行起来。

主要工作包括：

```text
接入真实事件
更新对象变量
推断对象状态
启动流程实例
校验规则和权限
占用和释放资源
调用算法模型
驱动 role agent 决策
调度仿真事件
管理当前世界和分支世界
执行 service / process
记录事件和审计
更新状态投影
跟踪执行效果
```

运行时回答的是：

```text
现在现场是什么状态？
发生了什么事件？
哪个流程正在执行？
哪个资源被占用？
哪个规则被触发？
算法模型输出了什么？
role agent 采取了什么建议？
哪些动作被执行？
执行结果如何？
```

设计时和运行时之间应通过版本化的 World Model 对齐。运行时不能脱离设计时随意产生新的业务语义，设计时的变化也不能无追溯地影响历史事件解释。

---

## 7. World Model 是唯一语义源

Agent Studio 中的 World Model 应被视为平台运行的唯一语义源。

所谓唯一语义源，是指对象、能力、流程、规则、事件、状态、权限、算法模型输入输出、role agent 可观察上下文，都应从同一套世界模型定义中派生，而不是各自维护一套割裂配置。

否则平台很容易变成配置拼盘：

```text
一套对象配置
一套流程配置
一套算法输入配置
一套 Agent Prompt 配置
一套权限配置
一套事件配置
一套状态配置
```

这些配置如果缺乏统一语义源，后续会出现模型不一致、规则重复、状态不可追溯、算法输入不稳定、Agent 决策边界不清等问题。

因此，Agent Studio 的推荐结构应是：

```text
World Model Definition
  → Runtime Registry
  → Object Schema
  → Service Schema
  → Process Schema
  → Rule Registry
  → Event Schema
  → State Projection
  → Model Service Context
  → Role Agent Context
  → Permission Policy
  → Audit Trace
```

一句话概括：

> **Agent Studio 的所有运行能力，都应是 World Model 在不同运行维度上的投影。**

---

## 8. 三类核心对象

Agent Studio 中的对象不应被强行统一成一种 Agent。

系统中应明确存在三类对象：

```text
Object
 ├── thing
 ├── role
 └── concept
```

这三类对象共享同一个 world、同一套关系网络、同一套事件体系、同一套规则体系、同一套审计机制，但不共享同一种主动性。

---

## 9. thing：现场执行对象

### 9.1 定义

`thing` 表示存在于物理世界或现场逻辑世界中的执行对象，包括设备、容器、运输单元、工位、库区、产线、能源介质管网等。

例如：

```text
转炉
连铸机
天车
钢包
铁包
废钢斗
加热炉
轧机
库位
运输轨道
能源介质管网
质量检测设备
```

### 9.2 核心职责

`thing` 的职责是：

```text
表达自身属性
表达自身变量
表达自身运行状态
暴露可调用能力
接收命令或流程调度
校验自身约束
执行动作
推进自身内部过程
产生状态变化
反馈事件
产生告警
支持审计
```

一句话定义：

> **thing 是可观测、可命令、可约束、可推进的现场执行单元。**

### 9.3 不应承担的职责

`thing` 不应承担：

```text
全局调度决策
多目标权衡
跨对象资源协调
开放式推理
复杂业务决策
绕过 service 的状态修改
直接修改业务对象状态
```

例如，转炉可以表达“是否空闲、是否可接收铁水、是否正在吹炼”，也可以执行“接收铁水、吹炼、出钢”等能力，但它不应自己决定整个炼钢区域的炉次顺序、天车优先级和连铸节奏。

---

## 10. role：认知与控制对象

### 10.1 定义

`role` 表示调度员、工艺员、班长、操作员、能源调度员、质量工程师等业务角色的智能体。

它更接近主动决策主体，可以由 LLM、规则、算法模型、工具调用、历史经验和人工确认机制共同驱动。

### 10.2 核心职责

`role` 的职责是：

```text
观察多个 thing 的状态
理解多个 concept 的业务语义
感知当前流程进展
识别异常和风险
调用算法模型
调用工具服务
发起 service 调用
启动或调整 process
进行任务分配
进行冲突消解
进行优先级判断
跟踪执行闭环
在异常情况下重规划
解释决策依据
```

一句话定义：

> **role 是世界中的认知、决策与指挥主体。**

### 10.3 不应承担的职责

`role` 不应承担：

```text
伪装成设备状态机
直接修改 thing.state
直接修改 thing.variables
绕过 thing.service 执行底层动作
承担设备内部的内生过程定义
绕过 runtime 直接控制现场对象
绕过规则和权限修改业务状态
```

role 的正确作用方式是：

```text
观察 world state
  → 理解业务目标
    → 调用算法模型或工具
      → 形成建议或决策
        → 通过 service / process 发起执行
          → runtime 校验规则、权限和资源
            → thing 执行能力
              → event 记录事实
                → state/status 更新
                  → role 跟踪反馈并必要时重规划
```

---

## 11. concept：业务语义对象

### 11.1 定义

`concept` 表示业务对象，而不是物理执行对象，也不是主动决策主体。

例如：

```text
ProductionOrder 生产订单
Heat 炉次
CastingPlan 浇次计划
TransportTask 运输任务
ScheduleTask 排程任务
MaterialLot 物料批次
QualityDecision 质量判定
EnergyPlan 能源计划
```

### 11.2 核心职责

`concept` 的职责是：

```text
承载业务语义
表达业务生命周期
表达业务状态
连接多个 thing
作为 role 决策上下文
作为流程执行目标
记录业务关系和业务历史
支撑审计和追溯
```

一句话定义：

> **concept 是共享业务事实，不是主动执行者。**

### 11.3 不应承担的职责

`concept` 不应承担：

```text
自主决策
自主调用工具
自主调度未来事件
主动下命令
直接控制 thing
成为第三种 runtime 主体
```

例如，`Heat` 可以表达“当前炉次处于兑铁中、吹炼中、待出钢、已完成”等业务状态，但它不应该自己去调用天车、控制转炉或修改设备状态。

---

## 12. 三类对象之间的关系

三类对象之间的关系可以概括为：

> **role 发起意图，process 组织协同，thing 执行能力，concept 承载业务语义，event 记录事实，state 表达结果。**

典型链路如下：

```text
role 观察 thing 和 concept
  → role 发起 service 调用或 process 执行
    → runtime 校验权限、规则和资源
      → process 组织一个或多个 thing 协同执行
        → thing 执行自身能力并反馈事件
          → runtime 更新 state / status
            → concept 被显式更新
              → role 根据反馈继续决策
```

更通俗地说：

```text
thing 管“能不能做、做没做、做到哪一步”
role 管“为什么做、现在该做什么、异常时怎么调整”
concept 管“这是哪件业务、处于什么业务阶段”
process 管“多个对象如何协同完成一件事”
event 管“发生过什么”
state/status 管“现在是什么样”
runtime 管“一切是否按规则、权限、资源和时间一致性运行”
```

---

## 13. Service：对象能力

### 13.1 定义

`Service` 表示对象对外暴露的能力。

它回答的问题是：

> **这个对象能做什么？**

在理论抽象上，Service 对应对象的 Behavior；在产品表达上，为了让用户更容易理解和配置，统一命名为 Service，即对象对外暴露的可调用能力。

对于 `thing` 来说，service 是它可以执行的动作或操作接口。

例如：

| 对象   | Service 示例                   |
| ------ | ------------------------------ |
| 转炉   | 接收铁水、接收废钢、吹炼、出钢 |
| 天车   | 吊运钢包、吊运铁包、吊运废钢斗 |
| 钢包   | 接收钢水、承载钢水、等待精炼   |
| 连铸机 | 开浇、停浇、换包               |
| 加热炉 | 装炉、出炉、加热               |
| 轧机   | 开轧、停轧、换辊、切换规格     |

对于 `role` 来说，service 可以表现为其可发起的指挥能力，例如：

```text
下达任务
调整顺序
触发重排
处理异常
确认执行结果
```

### 13.2 Service 与 Process 的区别

Service 只表达：

> **对象能做什么。**

Process 表达：

> **多个对象如何围绕某个业务目标协同完成一件事。**

例如：

```text
“转炉接收废钢”是转炉的 service；
“天车吊运废钢斗”是天车的 service；
“废钢斗倾倒废钢”是废钢斗的 service；
“兑废钢流程”则是多个 service 的协同组织。
```

因此，不能把复杂工业动作都塞进单个 service 中。

### 13.3 Service 的边界

Service 不应直接绕过 runtime 修改状态。

Service 的调用应遵循：

```text
调用意图
  → 权限校验
    → 规则校验
      → 资源校验
        → 执行动作
          → 产生事件
            → 更新状态投影
              → 记录审计
```

---

## 14. Process：过程与协同

### 14.1 定义

`Process` 用于表达一个或多个对象围绕某个业务目标展开的一段可执行过程。

例如：

```text
兑铁流程
兑废钢流程
吹炼流程
出钢流程
钢包吊运流程
连铸开浇流程
炉次生产流程
浇次组织流程
天车任务执行流程
能源调度流程
质量判定流程
```

一句话定义：

> **Process 是对象能力在特定业务目标下的组合编排，它定义参与对象、前置条件、调用能力、状态变化、事件输出和异常处理。**

### 14.2 Process 不是传统流程图

Process 不应被理解为传统意义上固化的流程图。

更准确地说：

> **流程是对象能力的组合，流程可以变化，但底层对象、能力和规则相对稳定。**

例如“兑废钢流程”并不是先画一个固定流程图，而是由以下稳定元素组装出来：

```text
Object:
- Converter
- Crane
- ScrapBucket
- Heat

Service:
- Converter.receiveScrap
- Crane.transportScrapBucket
- ScrapBucket.pourScrap

Rule:
- 转炉可接收废钢
- 废钢斗已到位
- 天车未被占用
- 安全联锁通过

Event:
- ScrapChargingStarted
- ScrapChargingCompleted

State Projection:
- Converter.state = ChargingScrap
- Heat.status = ScrapCharging
```

### 14.3 内生流程

内生流程主要描述单个 `thing` 内部可以根据自身规则推进的过程。

例如：

```text
吹炼开始后，根据工艺时间或模型预测进入吹炼结束；
加热过程根据时间和温度曲线推进；
设备运行一段时间后进入待机；
某个等待状态超过阈值后产生超时；
设备动作完成后自动切换状态。
```

这类流程体现 `thing` 的内生过程能力。

但需要强调：

> **内生流程不等于每个 thing 可以私有地控制未来事件和仿真时间轴。**

内生过程可以由 `thing` 定义，但未来事件的调度、取消、冲突处理和时间推进，应由统一的 runtime 或 simulation scheduler 管理。

### 14.4 协同流程

协同流程描述多个对象共同参与的过程。

例如“兑废钢流程”涉及：

```text
转炉
天车
废钢斗
当前炉次
安全联锁
调度规则
现场位置条件
资源占用关系
```

它不能被简单建模为转炉自己的内生事件。

更合理的表达是：

```text
Process: ScrapCharging

参与对象：
- Converter
- Crane
- ScrapBucket
- Heat

前置规则：
- 转炉处于可接收废钢状态
- 废钢斗已装载
- 废钢斗到达指定位置
- 天车可用或已被本流程占用
- 当前炉次等待兑废钢
- 安全联锁通过

执行过程：
- 占用天车
- 确认废钢斗位置
- 转炉进入接收废钢状态
- 废钢斗开始倾倒
- 废钢加入完成
- 释放相关资源

输出结果：
- 产生兑废钢开始事件
- 产生兑废钢完成事件
- 更新转炉状态
- 更新废钢斗状态
- 更新天车状态
- 更新炉次业务状态
```

所以，“兑废钢开始”不是转炉自己的纯内生事件，而是“兑废钢流程开始执行后产生的事实事件”。

---

## 15. Rule：规则与约束

### 15.1 定义

`Rule` 用于描述对象能力和流程执行的约束。

为了降低产品理解成本，不建议在前台区分过多规则类型，例如：

```text
constraint
precondition
policy
transition rule
scheduling rule
validation rule
safety rule
```

产品上可以统一称为“规则”。

### 15.2 规则是一等语义对象

Rule 不应只是流程或 Service 的附属配置，而应是独立、可复用、可审计的语义对象。

也就是说，规则可以被多个对象、多个能力、多个流程、多个 role agent、多个 model service 和 runtime 共同引用。

例如：

```text
Rule: 钢包未到位不可出钢

可被引用：
- Converter.TappingService
- SteelLadleTransportProcess
- SteelmakingSchedulerRole
- TappingTimeOptimizationModel
- Runtime execution validation
```

这意味着规则不是代码里的隐含判断，而是平台可查看、可复用、可审计、可参与运行时校验的约束定义。

### 15.3 规则挂载位置

规则可以挂载在三个层面：

| 规则位置 | 含义             | 示例                         |
| -------- | ---------------- | ---------------------------- |
| 对象规则 | 对象自身约束     | 转炉检修中不可接收铁水       |
| 能力规则 | service 调用条件 | 废钢斗到位才可接收废钢       |
| 流程规则 | process 推进条件 | 兑废钢完成后才可进入吹炼准备 |

### 15.4 规则的作用

规则不替代调度，也不替代算法。

规则主要提供边界：

```text
什么条件下允许执行
什么条件下需要等待
什么条件下必须报警
什么条件下必须取消
什么条件下需要人工确认
什么条件下禁止自动执行
```

规则是 runtime、role agent 和算法模型共同遵守的执行边界。

---

## 16. State ：状态表达

状态必须分层表达，不能为了统一而压成一种状态机制。

至少应区分：

| 状态类型        | 含义           | 示例                                   |
| --------------- | -------------- | -------------------------------------- |
| `thing.state`   | 物理或运行状态 | 空闲、运行中、故障、等待、装料中       |
| `concept.state` | 业务状态       | 待生产、兑铁中、吹炼中、待出钢、已完成 |
| `process.state` | 流程执行状态   | 待启动、运行中、暂停、完成、失败、取消 |
| `role.context`  | 决策上下文     | 当前目标、任务列表、异常处理上下文     |

例如，“兑废钢开始”发生后，系统可能同时更新：

```text
Converter.state = ChargingScrap
Crane.state = Busy
ScrapBucket.state = Pouring
Heat.state = ScrapCharging
ScrapChargingProcess.state = Running
```

这些状态虽然同时变化，但语义不同，不应混为一种通用 `state`。

### 16.1 状态不是事实本身

状态不是凭空修改出来的。

更合理的理解是：

> **状态是事件、流程和规则作用后的当前投影。**

例如：

```text
事件：ScrapChargingStarted

投影：
- Converter.state = ChargingScrap
- Heat.state = ScrapCharging
- Process.state = Running
```

因此，关键状态变化应有事件、流程实例和审计记录支撑。

可以将这一原则概括为：

> **事件记录事实，状态表达投影，规则解释边界，流程解释过程，审计解释责任。**

---

## 17. Event：事实记录

### 17.1 定义

`Event` 是已经发生的事实记录。

它回答的问题是：

> **发生过什么？什么时候发生？由谁触发？影响了谁？依据是什么？**

事件不应作为用户主要建模入口。

更推荐的原则是：

> **用户配置对象、能力、流程和规则；系统自动生成事件。**

### 17.2 事件不是日志

事件不能被简单理解为日志。

日志主要用于记录系统运行情况，而事件是世界模型运行中的事实单元。事件会驱动状态变化，触发规则判断，推进流程实例，支撑仿真回放，并形成审计依据。

因此，事件是连接对象、能力、规则、流程和状态的运行时纽带。

### 17.3 事件的作用

事件主要用于：

```text
驱动状态变化
记录事实
支撑审计
支撑回放
支撑复盘
支撑仿真
支撑异常追踪
支撑模型训练和效果评估
支撑决策责任追溯
```

### 17.4 事件示例

例如：

```text
铁包到达
兑铁流程开始
兑铁开始
兑铁完成
兑废钢开始
兑废钢完成
吹炼开始
吹炼结束
出钢开始
出钢完成
天车故障
流程取消
状态变更
调度建议产生
算法模型调用完成
人工确认通过
```

### 17.5 事件来源

为了兼容仿真和真实现场，每个事件都应记录来源信息。

建议事件具有：

```text
sourceType:
  - sensor
  - plc
  - scada
  - mes
  - l2
  - manual
  - simulation
  - prediction
  - inferred
  - algorithm
  - role_agent
```

同时建议记录：

```text
timestamp
sourceSystem
confidence
correlationId
relatedObjects
relatedProcess
relatedConcept
worldModelVersion
rawPayload
auditInfo
```

这样系统可以区分：

```text
真实采集事件
人工确认事件
仿真生成事件
预测事件
规则推断事件
算法输出事件
role agent 决策事件
```

---

## 18. 事件驱动与回写闭环

Agent Studio 的运行机制应采用事件驱动。

典型链路如下：

```text
事件发生
  → 进入 event store
    → 触发规则判断
      → 推进流程实例
        → 更新状态投影
          → role agent 观察到变化
            → 调用算法模型或工具
              → 形成建议
                → runtime 校验权限、规则和资源
                  → 调用 service / process
                    → 产生新的事件
                      → 状态再次更新
```

这形成一个完整的世界运行闭环。

### 18.1 回写的含义

在 Agent Studio 中，“回写”不是简单写数据库字段，也不是直接修改现场状态。

更准确地说：

> **回写是将分析、预测、推演或智能体决策结果，在规则、权限、安全和审计约束下，转化为对业务系统或现场执行系统的 service / process 调用。**

例如：

```text
分析 / 预测 / 推演结果
  → role agent 形成建议
    → runtime 校验权限、规则和资源
      → service / process 被调用
        → MES、L2、调度系统或现场执行系统被更新
          → 真实事件反馈回来
            → world state 再次更新
```

这样，Agent Studio 才能从“看见现场”走向“理解现场、推演现场、辅助决策、闭环执行”。

---

## 19. Agent Studio 不只是仿真平台

Agent Studio 不应被限定为离线仿真系统。

更准确地说：

> **仿真只是 Agent Studio 的一种运行模式。**

Agent Studio 应支持同一套世界模型在多种模式下运行：

| 运行模式     | 数据来源                                 | 核心作用                               |
| ------------ | ---------------------------------------- | -------------------------------------- |
| 离线仿真模式 | 人工设定初始状态、规则、流程、仿真事件   | 验证流程、规则、调度策略和异常场景     |
| 在线映射模式 | 传感器、PLC、SCADA、MES、L2 等现场数据   | 实时映射现场状态，形成在线工业世界模型 |
| 预测推演模式 | 当前真实状态 + 仿真规则 + 算法模型       | 推演未来风险、冲突和节奏变化           |
| 决策辅助模式 | 实时世界状态 + 算法模型 + role agent     | 为调度员、工艺员、班长等角色提供建议   |
| 闭环执行模式 | role agent + runtime + service / process | 在权限和安全边界内触发执行并跟踪反馈   |

因此，Agent Studio 的核心不是“模拟一个假的世界”，而是：

> **维护一个可运行的工业世界模型：真实数据用于校准当前世界，仿真机制用于推演未来世界，算法模型用于专业计算，role agent 用于组织决策，runtime 用于保证执行闭环。**

---

## 20. 内生仿真的重新理解

当前智能体如果完全依赖外部事件驱动，就会显得“不活”。这个判断是成立的。但需要进一步修正：

> **内生仿真不等于让每个 thing 自己随意产生未来事件。**

更合理的理解是：

```text
thing 可以定义自身内生流程；
process 可以定义跨对象协同流程；
runtime 统一校验规则和资源；
simulation scheduler 统一管理未来事件和仿真时间；
event 只记录已经确认发生的事实。
```

### 20.1 单对象内生演化

例如：

```text
吹炼过程根据时间分布推进；
加热过程根据温度模型推进；
等待状态超过阈值后触发超时；
设备执行动作后自动进入下一状态。
```

这类能力可以归属于 `thing.process`。

### 20.2 跨对象协同演化

例如：

```text
兑铁
兑废钢
出钢
吊包
开浇
钢包运输
```

这类过程不能简单归属于某个 `thing`，而应由 `process` 表达，由 runtime 统一协调。

### 20.3 兑铁、兑废钢的正确理解

“兑铁开始”或“兑废钢开始”不应简单判断为“转炉内生事件”或“外部事件”。

更准确地说：

```text
“铁包到达”是外部事实事件；
“启动兑铁流程”是 role、scheduler 或规则机制发起的流程调用；
“兑铁开始”是流程启动后产生的事实事件；
“兑铁完成”是流程执行完成后的事实事件；
“吹炼过程推进”更适合作为转炉内部的内生流程。
```

对于“兑废钢”同理。

“兑废钢开始”不应被理解为转炉自己内生生成的事件，而应理解为：

> **兑废钢流程在转炉、天车、废钢斗、炉次等对象条件满足后启动，并由流程运行产生的开始事实。**

---

## 21. 真实现场接入

Agent Studio 可以接入真实现场事件信号和各种 `thing` 的状态值。

接入现场后，平台会从“离线仿真世界”升级为“在线工业世界模型”。

典型链路如下：

```text
传感器 / PLC / SCADA / MES / L2 / 人工录入
  → 数据接入与事件适配
    → 更新 thing.variables
      → 推断 thing.state
        → 生成 event
          → 推进 process
            → 更新 concept.status
              → role agent 观察、判断、建议或执行
```

### 21.1 现场信号映射示例

| 现场信号         | 映射到 Agent Studio               |
| ---------------- | --------------------------------- |
| 转炉倾动角度变化 | Converter.variables.tiltAngle     |
| 氧枪下降到位     | Lance.state = InPosition          |
| 天车位置变化     | Crane.location                    |
| 铁包到达兑铁位   | HotMetalLadleArrived event        |
| 炉次号绑定       | Heat 与 Converter 建立 link       |
| MES 下发作业计划 | ProductionTask / HeatPlan concept |
| 兑铁实际开始     | HotMetalChargingStarted event     |
| 兑铁实际完成     | HotMetalChargingCompleted event   |

### 21.2 真实事件与仿真事件的关系

接入现场后，应坚持一个原则：

> **真实事件优先，仿真事件用于预测、补全和推演。**

在在线运行时，真实事件应覆盖或取消对应的预测事件。

例如，如果现场已经采集到：

```text
兑铁开始时间 = 10:03:20
```

平台就不应再使用仿真分布生成另一个“兑铁开始时间”。

但如果真实事件尚未发生，平台可以基于当前状态预测未来：

```text
当前铁包已到位
转炉空闲
天车预计 2 分钟后释放
→ 预计 2~4 分钟后可启动兑铁流程
```

---

## 22. 当前世界与分支世界

为了同时支持真实现场和仿真推演，建议引入两个运行层次：

```text
Current World 当前世界
Branch World 分支世界
```

### 22.1 当前世界 Current World

当前世界由真实事件和真实状态驱动，表示现场现在真实是什么样。

例如：

```text
1#转炉正在吹炼
3#天车正在吊运钢包
Heat#001 处于吹炼中
2#精炼炉预计 12 分钟后空闲
```

当前世界应以真实事件为准。

### 22.2 分支世界 Branch World

分支世界从当前世界复制一个状态快照，然后用于未来推演。

它回答的问题是：

> **如果这样调度，未来可能怎样？**

例如：

```text
方案 A：优先 1#转炉出钢
方案 B：优先处理 2#转炉异常
方案 C：调整 3#天车任务顺序
```

每个方案都可以在分支世界中仿真，比较：

```text
连铸等待时间
转炉等待时间
天车冲突次数
钢包周转时间
温降风险
计划偏离量
能源消耗
质量风险
```

这使 Agent Studio 不只是“看现场”，而可以“推演未来”和“辅助决策”。

---

## 23. 算法模型与平台的关系

role agent 要做复杂决策，而复杂决策背后往往需要算法模型支撑。

例如：

```text
生产排程算法
天车调度算法
钢包周转优化算法
温降预测模型
出钢时间预测模型
连铸节奏预测模型
能源平衡优化模型
质量判定模型
风险诊断模型
多目标优化模型
```

但需要明确：

> **Agent Studio 不是算法平台本身，也不替代专业算法模型。**

更准确地说：

> **Agent Studio 是算法模型运行、协同、被调用、被验证、被闭环执行的工业世界底座。**

### 23.1 平台和算法的分工

| 角色         | 负责什么                                         |
| ------------ | ------------------------------------------------ |
| Agent Studio | 描述世界、维护状态、组织流程、约束执行、记录事件 |
| 算法模型     | 预测、优化、匹配、排序、诊断、评估               |
| role agent   | 理解目标、选择模型、组织决策、解释结果、发起执行 |
| runtime      | 校验权限、规则、资源，推进流程并记录闭环         |

一句话概括：

> **算法模型负责“算”，Agent Studio 负责“让算法知道算什么、基于什么算、算完怎么用、用了以后效果如何”。**

---

## 24. 算法模型作为 Model Service

为了保持产品概念简洁，建议不要在前台新增过重的“算法模型对象”。

可以把算法模型看作一种特殊的 service：

> **Model Service / Algorithm Service / Decision Service**

它与普通 service 的区别是：

| 类型          | 作用                 | 示例                                   |
| ------------- | -------------------- | -------------------------------------- |
| 普通 Service  | 执行现场动作         | 转炉出钢、天车吊运、钢包接收           |
| Model Service | 产生预测、判断或方案 | 排程优化、路径规划、质量预测、能源预测 |
| Tool Service  | 查询或辅助处理       | 查库存、查计划、查历史事件             |

例如：

```text
SchedulingOptimizationService
CraneDispatchModel
QualityPredictionModel
EnergyBalanceOptimizer
BlowingEndTimePredictor
LadleTemperatureDropModel
CastingRhythmPredictor
```

这些模型不直接改状态，也不直接控制设备。

它们输出的是：

```text
预测结果
评分结果
推荐方案
排序结果
风险判断
约束冲突
候选动作
方案评价
```

最终是否执行，应由 role agent、runtime、规则和权限共同决定。

---

## 25. 平台为算法模型提供的能力

Agent Studio 至少可以为算法模型提供六类能力。

### 25.1 统一输入

平台维护结构化 world state，因此可以给算法提供统一输入：

```text
world snapshot
object states
process states
concept status
resource availability
event history
rules and constraints
```

算法不需要自己到处取数、清洗、拼接和理解业务含义。

### 25.2 约束边界

平台可以向算法提供现场约束：

```text
钢包未到位不能出钢
天车不能同时执行两个任务
精炼炉未空闲不能接收钢水
温降超过阈值方案不可用
安全联锁未通过不能执行
```

算法可以在生成方案时使用这些约束，runtime 也可以在执行前二次校验。

### 25.3 候选动作空间

平台可以告诉算法：

```text
当前哪些 service 可以调用
当前哪些 process 可以启动
哪些对象可用
哪些资源已被占用
哪些动作被禁止
哪些动作需要人工确认
```

这样算法输出的方案更接近可执行。

### 25.4 仿真评估环境

算法可以输出多个候选方案，平台在分支世界中推演和比较。

例如：

```text
方案 A：优先 1#转炉出钢
方案 B：优先 2#转炉出钢
方案 C：调整 3#天车任务顺序
```

平台可比较：

```text
转炉等待时间
连铸等待风险
天车冲突次数
钢包周转时间
温降风险
计划偏离量
```

### 25.5 执行闭环

算法输出建议后，平台负责将建议转化为可执行动作：

```text
模型输出建议
  → role agent 理解和选择
    → runtime 校验规则和权限
      → process 启动
        → thing.service 执行
          → event 记录事实
            → state/status 更新
```

### 25.6 模型治理与复盘

平台可以记录：

```text
当时输入是什么
调用了哪个模型
模型版本是什么
模型输出了什么
role agent 是否采纳
人是否确认
实际执行了什么
最终效果如何
```

这可用于：

```text
模型效果评估
调度策略复盘
算法版本对比
参数优化
责任审计
持续学习
```

---

## 26. 推理分级原则

Agent Studio 不能把所有决策都交给大模型，也不能把所有规则都写死在代码里。

推荐采用推理分级机制：

```text
确定性规则由 Rule Engine / Runtime 执行；
专业计算由 Model Service 执行；
语义理解、方案组织和异常解释由 role agent 执行；
现场动作必须通过 Service / Process 执行。
```

具体分工如下：

| 类型               | 适合承担者            | 示例                                   |
| ------------------ | --------------------- | -------------------------------------- |
| 确定性规则校验     | runtime / rule engine | 钢包未到位不能出钢                     |
| 复杂数值计算       | model service         | 天车路径优化、温降预测                 |
| 语义理解与意图识别 | role agent / LLM      | 用户说“连铸不能断”，识别为节奏保持目标 |
| 多方案组织与解释   | role agent            | 比较多个算法候选方案并解释原因         |
| 最终执行校验       | runtime               | 权限、资源、状态、安全边界检查         |

硬边界是：

```text
LLM 不直接控制现场；
算法模型不直接修改状态；
role agent 不绕过 runtime；
runtime 不绕过规则；
thing 不承担全局决策；
concept 不主动执行。
```

---

## 27. role agent、算法模型和平台的协同关系

可以把三者关系理解为：

> **Agent Studio 是工业智能体的操作系统，算法模型是可插拔的专业决策组件，role agent 是使用这些组件完成业务决策的智能角色。**

典型链路如下：

```text
World Model 提供现场语义和状态
  → Algorithm Model 提供预测、优化和评估
    → Role Agent 组织判断和决策
      → Runtime 校验并执行
        → Event / State 形成反馈闭环
```

### 27.1 role agent 不是替代算法

role agent 不应该把所有复杂计算都放到 LLM prompt 中完成。

例如，炼钢调度员 agent 不应该只靠语言推理决定天车最优调度方案，而应调用：

```text
天车冲突检测模型
钢包周转优化模型
连铸节奏预测模型
多目标评价模型
```

role agent 负责：

```text
识别问题
选择算法
解释算法输出
比较候选方案
结合规则和上下文做决策
发起流程执行
跟踪执行结果
```

算法负责：

```text
算得准
算得快
算得可验证
```

平台负责：

```text
给算法提供结构化输入
给决策提供执行边界
给执行提供闭环机制
```

---

## 28. Runtime：运行时职责

Agent Studio 的 runtime 是保证世界模型能够运行起来的核心。

它的职责包括：

```text
接收 role 或系统规则发起的 service / process 调用
校验权限
校验对象状态
校验流程前置条件
占用和释放资源
推进流程实例
调度未来事件
消费事件并更新状态
同步真实现场状态
管理仿真时间
管理当前世界和分支世界
调用算法模型
记录审计日志
在异常情况下取消、暂停或重排流程
```

尤其需要强调：

> **未来事件和仿真时间轴不应由每个 thing 私有控制，而应由 simulation scheduler 或全局 runtime 统一调度。**

否则会出现：

```text
全局时间不一致
多个对象争用同一资源
前置条件失效后未来事件无法取消
上下游联动失真
仿真结果不可解释
在线状态和预测状态互相污染
```

---

## 29. 权限与控制边界

如果 `role` 最终目标是“直接下命令并闭环执行”，则必须明确控制边界。

建议形成以下硬约束：

```text
1. role 不能直接修改 thing.variables 或 thing.state；
2. role 只能通过 thing.service 或 process 影响现场对象；
3. thing 不应随意修改 concept.status；
4. concept.status 应由流程运行、role 确认或系统规则显式维护；
5. 跨对象动作不应由单个 thing 私有发起；
6. 涉及资源占用、位置约束、业务许可的动作，应通过 process 执行；
7. 算法模型不能直接控制现场对象；
8. 所有关键状态变化都应有事件和审计记录支撑。
```

控制路径应保持清楚：

```text
role 决策
  → 调用 model service / tool service
    → 形成建议或方案
      → 调用 service / process
        → runtime 校验规则
          → thing 执行能力
            → event 记录事实
              → state/status 更新
                → role 跟踪闭环
```

---

## 30. 模型版本与事件溯源

Agent Studio 应引入 world model version。

所有关键事件、流程实例、模型调用记录、状态投影和审计记录，都应携带其发生时对应的世界模型版本。

否则会出现历史解释漂移问题：

```text
同一个 Heat.status，依据哪个版本的状态机解释？
同一个调度建议，依据哪个版本的规则生成？
同一个仿真分支，依据哪个版本的工艺流程推演？
同一个算法输出，依据哪个版本的 world schema 输入？
```

建议原则是：

> **历史事件应按照事件发生时的 World Model Version 解释，而不是简单使用最新版本解释。**

这对工业系统尤其关键，因为现场事件、仿真事件、预测事件、算法事件和人工确认事件往往交织在一起。如果没有版本约束，复盘和审计会失去可信基础。

---

## 31. 推荐的 Schema 收敛方向

不建议追求一个“所有对象完全同构”的超级统一 Schema。

更稳妥的做法是：

### 31.1 抽象 Base Object Schema

只放所有对象共有的字段：

```text
metadata
identifiers
name
type
description
tags
links
audit
worldModelVersion
```

### 31.2 在 Base Object 上区分三类对象

```text
thing schema
role schema
concept schema
```

### 31.3 在对象之外定义通用运行模型

包括：

```text
service schema
process schema
rule schema
event schema
state model
model service schema
runtime context
```

产品前台重点暴露：

```text
对象
能力
流程
规则
状态
事件记录
模型服务调用关系
```

技术后台再维护：

```text
service invocation
process instance
resource lock
simulation scheduler
state projection
branch world
model execution record
audit log
```

---

## 32. 三类对象的最小字段建议

### 32.1 thing model

建议字段：

```text
metadata
attributes
variables
state
services
rules
processes
events
alarms
links
audit
```

字段含义：

```text
attributes：静态属性
variables：动态变量
state：运行状态
services：可执行能力
rules：自身约束
processes：内部过程或参与流程
events：事件记录
alarms：告警
links：与其他对象关系
audit：审计记录
```

不应包含：

```text
LLM prompt
开放式规划策略
全局调度策略
多目标决策逻辑
绕过 service 的状态修改脚本
```

### 32.2 role model

建议字段：

```text
metadata
responsibilityScope
goals
contextSources
tools
modelServices
services
policies
memory
plans
permissions
audit
```

字段含义：

```text
responsibilityScope：职责范围
goals：目标
contextSources：可观察对象和数据
tools：可调用工具
modelServices：可调用算法模型
services：role 可发起的动作
policies：决策约束
memory：记忆
plans：计划
permissions：权限
audit：审计记录
```

不应包含：

```text
设备级细粒度状态机
直接物理变量
设备内生过程定义
直接修改 thing.state 的能力
绕过 runtime 的现场控制能力
```

### 32.3 concept model

建议字段：

```text
metadata
properties
status
lifecycle
links
ownership
references
audit
```

字段含义：

```text
properties：业务属性
status：业务状态
lifecycle：生命周期
links：与对象、流程、任务之间的关系
ownership：责任归属
references：引用关系
audit：变更历史
```

不应包含：

```text
services
tools
自主 trigger runtime
自主计划
自主未来事件调度
直接控制 thing 的能力
```

---

## 33. Model Service 的最小字段建议

算法模型可以作为 `Model Service` 注册到平台中。

建议字段：

```text
metadata
modelType
inputSchema
outputSchema
requiredContext
constraints
version
owner
executionMode
timeout
confidenceOutput
explainability
audit
```

字段说明：

```text
modelType：预测、优化、诊断、评估、匹配等
inputSchema：输入结构
outputSchema：输出结构
requiredContext：需要哪些 world state
constraints：模型适用边界
version：模型版本
owner：模型责任人
executionMode：同步、异步、批处理、在线调用
timeout：调用超时
confidenceOutput：是否输出置信度
explainability：是否输出解释
audit：调用审计
```

Model Service 输出不应直接改变 world state，而应成为 role agent 和 runtime 的决策输入。

---

## 34. 产品建模路径

在 Agent Studio 的界面和文档中，可以引导用户按照以下路径建模：

```text
第一步：定义对象
  - 有哪些 thing？
  - 有哪些 role？
  - 有哪些 concept？

第二步：定义能力
  - 每个 thing 能做什么？
  - 每个 role 能发起什么？
  - 哪些算法模型可作为 model service 调用？

第三步：定义流程
  - 哪些对象要协同完成一件事？
  - 流程如何开始、推进、完成、异常退出？

第四步：定义规则
  - 什么条件下允许执行？
  - 什么条件下需要等待、报警、取消或人工确认？

第五步：接入数据
  - 哪些状态来自传感器？
  - 哪些事件来自 MES / SCADA / L2？
  - 哪些数据来自人工确认？
  - 哪些事件由仿真或预测产生？

第六步：运行世界
  - runtime 推进流程
  - scheduler 管理时间
  - event 记录事实
  - state/status 表达当前结果
  - model service 支撑决策
  - role agent 组织闭环
```

---

## 35. 钢铁场景示例：炼钢调度员 Agent

以炼钢调度员 `role agent` 为例。

### 35.1 观察对象

它可以观察：

```text
转炉状态
天车位置
钢包状态
铁包状态
废钢斗状态
精炼炉状态
连铸机节奏
炉次状态
浇次计划
当前异常事件
未来预测风险
```

### 35.2 可调用模型

它可以调用：

```text
出钢时间预测模型
连铸节奏预测模型
天车冲突检测模型
钢包周转优化模型
温降预测模型
炉次排序优化模型
```

### 35.3 决策过程

典型过程：

```text
观察当前 world state
  → 发现 20 分钟后可能连铸断浇
    → 调用连铸节奏预测模型
      → 调用钢包周转优化模型
        → 调用天车冲突检测模型
          → 生成多个候选方案
            → 在分支世界中推演
              → 比较方案效果
                → 给出建议
                  → 人工确认或自动触发流程
                    → 跟踪执行反馈
```

### 35.4 输出结果

role agent 可以输出：

```text
建议将 3#天车优先分配给 1#转炉钢包；
建议延后 2#转炉出钢 3 分钟；
该方案预计可降低连铸等待风险；
该方案不会引发新的天车路径冲突；
需调度员确认后执行。
```

执行后，runtime 会记录：

```text
建议来源
调用模型
输入状态
输出方案
人工确认
实际执行事件
最终效果
```

---

## 36. 平台可信度与评测指标

Agent Studio 不仅要让 role agent 能决策，还要评估它为什么这样决策、决策是否被采纳、执行效果如何、是否优于人工方案、是否存在模型漂移。

建议建立以下评测指标：

```text
建议采纳率
人工修改率
执行成功率
规则冲突率
仿真预测偏差
算法模型误差
role agent 解释一致性
事件识别准确率
状态投影准确率
分支世界推演命中率
模型调用成功率
决策闭环完成率
异常处理有效率
```

这些指标用于支撑：

```text
模型治理
算法优化
调度策略复盘
智能体能力评估
现场运行可信度提升
```

没有评测和复盘，Agent Studio 很容易停留在“看起来很智能”的阶段；有了评测闭环，平台才能真正走向可信工业智能系统。

---

## 37. Agent Studio 的最终定位

Agent Studio 不应被理解为：

```text
单纯的仿真平台
单纯的 Agent 托管平台
单纯的算法平台
单纯的数据采集平台
单纯的流程编排平台
```

更准确的定位是：

> **Agent Studio 是一个面向工业现场的本体化世界模型运行平台。它以 thing、role、concept 三类对象为基础，以 service 表达对象能力，以 process 组织对象协同，以 rule 约束执行边界，以 state 表达当前结果，以 event 记录世界变化，以 model service 支撑专业决策，以 runtime 保证时间、资源、状态和执行闭环的一致性。**

在这个体系中：

```text
thing 负责现场执行和局部内生过程；
role 负责观察、判断、调用模型、发起流程和跟踪闭环；
concept 负责承载业务语义和生命周期；
service 负责表达对象能力；
process 负责组织单对象或跨对象过程；
rule 负责表达执行边界；
state/status 负责表达当前结果；
event 负责记录已经发生的事实；
model service 负责提供预测、优化、诊断和评估能力；
runtime / scheduler 负责统一调度时间、资源、流程和状态变化；
current world 表示真实现场；
branch world 用于预测推演和方案比较。
```

最终目标不是做一个概念复杂的平台，而是做一个：

> **能让工业现场对象“活起来”、让真实数据“映射进来”、让仿真推演“跑起来”、让算法模型“用起来”、让智能体决策“落下去”、让执行结果“可追溯”的 Agent Studio。**

一句话总结：

> **真实事件驱动当前世界，仿真机制推演未来世界，算法模型提供专业计算，role agent 组织决策闭环，runtime 保证一切在规则、权限和审计之下运行。**