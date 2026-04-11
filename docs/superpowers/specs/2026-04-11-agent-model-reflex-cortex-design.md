# Agent Studio Agent Model Evolution Design

## Goal
在保持 `model.json` 扁平结构和较低配置认知负担的前提下，将当前“数字孪生/物模型 + 反应式行为”模型演进为统一的智能体模型，使其同时覆盖：

- 实体型 agent：具身重、`reflex` 强、`cortex` 轻
- 调度型 agent：具身轻、`reflex` 适中、`cortex` 强

目标不是拆出两套 schema，而是在一套统一 schema 中表达不同能力重心的 agent。

## Core Position

### 1. 智能体优先
统一抽象以 “agent” 为核心，不再把 “thing model” 和 “agent model” 视为并列体系。

- 物模型是 agent 的具身部分
- `reflex` 是 agent 的快速、确定性响应系统
- `cortex` 是 agent 的慢速、权衡式决策系统

### 2. 概念分层，配置扁平
`embodiment / reflex / cortex` 只作为概念与引擎视角存在，不作为配置文件中的独立层级。

配置作者继续面对扁平顶层结构，避免引入新的大块嵌套和学习成本。

### 3. 向后兼容优先
保留当前大部分顶层字段与语义，新增最小数量的字段来显式表达 `cortex`，并通过校验规则收紧现有边界。

## Design Principles

### 1. 单一 schema，能力可裁剪
所有 agent 共用一份 schema，但不要求每个 agent 都同时具备全部能力模块。

- 实体型 agent 可以具备完整的具身与 `reflex`，只配置少量 `cortex`
- 调度型 agent 可以弱化具身，强化 `goals / decisionPolicies / memory / plans`

### 2. `reflex` 与 `cortex` 的职责分界

`reflex` 负责：
- 快速响应
- 局部确定性判断
- 硬约束执行
- 状态机流转
- 定时检查和异常响应

`cortex` 负责：
- 多目标权衡
- 冲突处理
- 计划生成
- 策略选择
- 跨实体或跨步骤的决策

### 3. `cortex` 不绕过硬约束
无论 agent 是否进入 `cortex`，所有高层决策都必须服从 `rules`、权限、状态机约束与安全边界。

### 4. 模型定义与实例运行态分离
- `model.json` 描述“这种 agent 是什么、能做什么、如何响应、允许如何思考”
- 实例文件描述“这个 agent 现在是什么状态、绑定了什么数据源、记住了什么、正在执行什么计划”

## Recommended Flat Schema

推荐保留以下顶层字段：

```json
{
  "$schema": "https://agent-studio.io/schema/v2",
  "metadata": {},
  "attributes": {},
  "variables": {},
  "derivedProperties": {},
  "rules": {},
  "functions": {},
  "services": {},
  "states": {},
  "transitions": {},
  "behaviors": {},
  "events": {},
  "alarms": {},
  "schedules": {},
  "goals": {},
  "decisionPolicies": {},
  "memory": {},
  "plans": {}
}
```

其中：

- `attributes / variables / derivedProperties` 承载具身信息
- `rules / services / states / transitions / behaviors / events / alarms / schedules` 承载 `reflex`
- `goals / decisionPolicies / memory / plans` 承载 `cortex`

该归属关系只用于方法论和引擎实现，不要求配置者在 JSON 中再学习一层新的分组。

## Requiredness Rules

### 最小必选项
为保证 schema 既统一又足够灵活，必选项应尽量少。

推荐的最小必选项：

- `$schema`
- `metadata.name`
- `metadata.title`

同时要求模型至少具备以下之一：

- `attributes`
- `variables`
- `services`
- `goals`

这样可以同时覆盖：

- 以具身和状态为核心的实体型 agent
- 以动作和协调为核心的执行型 agent
- 以目标与策略为核心的调度型 agent

### 条件必选项
以下字段不是全局必选，但一旦出现就必须满足关联约束：

- 存在 `derivedProperties` 时，其引用的 `attributes / variables` 必须存在
- 存在 `transitions` 时，必须存在 `states`
- 存在 `decisionPolicies` 时，其引用的 `goals / memory / plans` 必须存在
- 存在 `alarms / behaviors / schedules` 时，其动作引用的 `events / services / actions` 必须存在

## Field-Level Decisions

### 保留并延续的字段
以下字段保留，继续作为统一 schema 的核心骨架：

- `metadata`
- `attributes`
- `variables`
- `derivedProperties`
- `rules`
- `functions`
- `services`
- `states`
- `transitions`
- `behaviors`
- `events`
- `alarms`
- `schedules`

### 新增字段
为显式表达 `cortex`，新增以下顶层字段：

- `goals`
- `decisionPolicies`
- `memory`
- `plans`

推荐分阶段引入：

1. 第一阶段引入 `goals` 与 `decisionPolicies`
2. 第二阶段引入 `memory` 与 `plans`

### 字段职责收口

#### `functions`
必须是严格无副作用的纯计算或查询逻辑。

- 允许读取 `attributes / variables / derivedProperties`
- 不允许写入任何变量、记忆或状态

#### `services`
作为统一动作入口，承载可执行命令。

- 可以由人工、系统、`reflex`、`cortex` 触发
- 推荐所有可复用动作最终都收口到 `services`

#### `rules`
仅表达硬约束、校验和安全边界，不表达目标优化逻辑。

适合放入 `rules` 的内容：
- 容量上限
- 安全温度范围
- 权限控制
- 状态前置条件

不适合放入 `rules` 的内容：
- 吞吐最大化
- 等待时间最小化
- 高优先级任务优先

这些内容应进入 `goals` 或 `decisionPolicies`。

#### `states / transitions`
仅表达快速、确定性的 `reflex` 状态机，不承担高层策略选择。

#### `variables.status`
不能与实例层 `state` 语义重叠。

推荐约束：
- `state` 表示内部 `reflex` 状态机状态
- `variables.status` 如保留，只表示外部可观测业务状态

## Model vs Instance Split

### `model.json` 承载的内容
`model.json` 是模型定义文件，应描述结构、契约与能力模板，而不是当前运行值。

应包含：

- 元数据定义
- 属性与变量定义
- 派生属性定义
- 规则、服务、状态机、行为、事件、告警、调度定义
- 目标定义
- 决策策略定义
- 记忆槽位定义
- 计划结构定义

### 实例文件承载的内容
实例文件是运行态数据，应描述某个具体 agent 当前的值和上下文。

推荐实例结构包含：

- `id`
- `modelId`
- `metadata`
- `state`
- `attributes`
- `variables`
- `bindings`
- `memory`
- `activeGoals`
- `currentPlan`
- `extensions`

### `bindings` 的位置
当前实例将 `bind` 内嵌到 `variables.xxx` 中，这会混合“内部状态定义”和“外部接线方式”。

推荐调整为：

- `variables.temperature = 1650`
- `bindings.temperature.source = "plc_line_a"`

这样可以清晰区分：

- `variables`：agent 当前内部状态
- `bindings`：实例如何从外部系统感知或同步数据

## Agent Types on the Same Schema

### 实体型 agent
例如钢包、天车、设备单元。

特点：
- `attributes / variables / derivedProperties` 较重
- `rules / states / transitions / alarms / schedules / services` 较重
- `goals / decisionPolicies / memory / plans` 可先轻量

适合的 `cortex` 范围：
- 当前任务选择
- 异常工况下的动作切换
- 简单路线或目标冲突处理

### 调度型 agent
例如产线调度、工艺协调、全局优化代理。

特点：
- `attributes` 可以很少
- `variables` 主要是全局运行态摘要
- `goals / decisionPolicies / memory / plans` 较重
- `services` 更像协调动作接口

适合的 `cortex` 范围：
- 多资源冲突消解
- 多目标权衡
- 中短期计划生成
- 协调多个实体 agent

## Migration Strategy

### Phase 1: 收紧现有 schema 边界
先把当前模型稳定为“具身 + `reflex`”的干净模板。

应优先完成：

1. 补齐所有被引用但未定义的变量、属性、规则
2. 明确 `functions` 无副作用
3. 明确 `services` 是标准动作入口
4. 区分 `state` 与 `variables.status`
5. 拆分实例中的字段定义、字段值、数据绑定

### Phase 2: 最小化引入 `cortex`
新增：

- `goals`
- `decisionPolicies`

目标是在不显著增加配置复杂度的前提下，让 schema 从“可执行物模型”升级为“hybrid agent model”。

### Phase 3: 补充运行时认知结构
新增或逐步丰富：

- `memory`
- `plans`

这一步主要服务于运行引擎和实例态演进，而不是 schema 主体重写。

## Validation Rules

建议优先实现以下校验规则：

### 1. 引用完整性校验
所有表达式和动作引用到的字段都必须存在。

覆盖对象：
- `derivedProperties`
- `rules`
- `transitions`
- `behaviors`
- `alarms`
- `schedules`
- `decisionPolicies`
- `plans`

### 2. 角色边界校验
- `functions` 不允许写状态
- `rules` 不允许产生副作用
- `transitions / behaviors / schedules` 的副作用应通过统一 action 或 `service` 承载

### 3. 状态机一致性校验
- 存在 `transitions` 时必须存在 `states`
- `initialState` 只能有一个
- `from / to` 必须引用合法状态

### 4. `cortex` 引用校验
- `decisionPolicies` 引用的 `goal`、`memory` 槽位、`plan` 类型必须存在
- `plans` 引用的执行动作必须能映射到现有 `services` 或标准 action

### 5. 模型与实例职责校验
- `model.json` 不能出现实例运行值
- 实例文件不能重复完整字段定义
- `bindings` 只能出现在实例层

## Immediate Issues Found in Current Files

当前 `model.json` 与实例文件中存在一些会阻碍后续演进的问题，需要在 Phase 1 先修正：

1. 有规则引用未定义
   `temperatureNotRisingNaturally` 被引用但未定义。

2. 有字段被使用但未声明
   `usageCount`、`refractoryLife`、`targetLocation` 在逻辑中出现，但未在模型中正式定义。

3. 命名与语义不一致
   `temperatureExceeded.warning` 的触发条件实际是装载率，不是温度。

4. `functions` 存在副作用
   `calculateTemperatureDrop` 会写 `lastTempCheckTime`，违反纯函数边界。

5. 实例层结构混合了定义和值
   当前实例文件同时承载了字段说明、字段值和绑定信息，不利于后续增加 `memory` 与 `currentPlan`。

## Out of Scope

本设计不包含以下内容：

- 具体运行引擎实现
- LLM 或规划器的技术选型
- OpenAPI 接口修改细节
- 数据库表结构的具体迁移 SQL
- 前端编辑器交互设计

## Final Recommendation

推荐采用“智能体优先、配置扁平、兼容演进”的方案：

1. 不拆分成独立的 thing model 与 agent model
2. 不新增 `embodiment / reflex / cortex` 三层配置结构
3. 保留当前顶层字段骨架
4. 通过 `goals / decisionPolicies / memory / plans` 最小增量补出 `cortex`
5. 通过校验规则和实例结构整理收紧边界

这样可以在保持低配置门槛的同时，让 Agent Studio 的模型从“数字孪生配置”自然演进为“统一的 hybrid agent schema”。
