# Agent Studio 智能体模型方法论

## 1. 核心立场

### 1.1 智能体优先
Agent Studio 统一以 **agent** 作为核心抽象，不再把“物模型”和“智能体模型”看成两套平行体系。

- 物模型是 agent 的**具身部分**
- `reflex` 是 agent 的**快速响应系统**
- `cortex` 是 agent 的**慢速决策系统**

这意味着：

- 钢包、天车、设备单元可以是 agent
- 产线调度、工艺协调、资源编排也可以是 agent
- 它们使用同一份顶层 schema，只是能力重心不同

### 1.2 概念分层，配置扁平
`embodiment / reflex / cortex` 是方法论分层和引擎视角，不是配置文件中的独立嵌套块。

配置作者面对的仍然是一份扁平顶层结构，例如：

- `attributes`
- `variables`
- `rules`
- `services`
- `states`
- `goals`
- `decisionPolicies`
- `memory`
- `plans`

这样做的目标是同时满足：

- 抽象清晰
- 配置成本低
- 向后兼容强

### 1.3 向后兼容优先
v2 schema 采用“保留骨架、补齐语义、收紧边界”的演进策略。

- 保留现有 `attributes / variables / rules / services / states / transitions / behaviors / alarms / schedules`
- 新增 `goals / decisionPolicies / memory / plans`
- 通过校验器保证职责边界，而不是通过继续增加配置层级来解决混乱

## 2. 顶层结构

推荐的 v2 顶层结构如下：

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

### 2.1 具身相关字段

- `attributes`: agent 的稳定特征或配置边界
- `variables`: agent 的运行时状态
- `derivedProperties`: 基于属性和变量计算得出的派生视图

### 2.2 `reflex` 相关字段

- `rules`: 硬约束、校验、权限和安全边界
- `functions`: 纯计算或查询逻辑
- `services`: 标准动作入口
- `states / transitions`: 快速、确定性的状态机
- `behaviors`: 全局事件响应
- `events`: 事件契约
- `alarms`: 告警生命周期定义
- `schedules`: 基于时间的检查与动作

### 2.3 `cortex` 相关字段

- `goals`: agent 追求的目标
- `decisionPolicies`: 何时由 `reflex` 升级到 `cortex`，以及决策时必须遵守的边界
- `memory`: 决策上下文槽位定义
- `plans`: `cortex` 输出的结构化计划模板

## 3. `reflex` 与 `cortex` 的职责边界

### 3.1 `reflex`
`reflex` 适合表达：

- 快速响应
- 局部判断
- 确定性流转
- 硬约束执行
- 定时检查
- 异常触发

常见场景：

- 温度超限拒绝执行
- 钢包满载时发出移动预警
- 到达寿命阈值时自动进入维护状态

### 3.2 `cortex`
`cortex` 适合表达：

- 多目标权衡
- 异常场景下的策略切换
- 计划生成
- 跨实体协调
- 慢速、代价较高的决策

常见场景：

- 运输冲突下的任务重排
- 安全与时效目标冲突时的权衡
- 调度 agent 对多个钢包的路径与工位分配

### 3.3 硬约束优先
`cortex` 不能绕过：

- `rules`
- 权限校验
- 状态机前置约束
- 安全边界

也就是说：

- `cortex` 可以决定“下一步做什么”
- 但不能决定“忽略容量上限和安全门禁”

## 4. 字段职责规则

### 4.1 `functions` 必须纯
`functions` 只允许读取上下文，不允许写入：

- `variables`
- `attributes`
- `memory`
- `state`

`functions` 的用途是：

- 查询
- 计算
- 模拟评估

凡是会修改运行态的逻辑，都应进入 `services`、状态动作、调度动作或计划执行器。

### 4.2 `services` 是统一动作入口
`services` 是 agent 可被调用的命令面。

- 可由人工调用
- 可由系统调用
- 可由 `reflex` 触发
- 可由 `cortex` 计划落地

建议：

- 能复用的动作尽量收口到 `services`
- `plans` 中的执行步骤优先引用 `services`

### 4.3 `rules` 只放硬约束，不放目标优化
适合放进 `rules`：

- 容量上限
- 安全温度范围
- 权限校验
- 机械门禁
- 状态前置条件

不适合放进 `rules`：

- 吞吐最大化
- 等待时间最小化
- 优先保障高等级订单

这些属于 `goals` 或 `decisionPolicies` 的范畴。

### 4.4 `state` 与业务状态分离
实例层 `state` 表示 **内部 `reflex` 状态机状态**。

如果需要额外暴露外部业务状态，应使用独立变量名，例如：

- `processStatus`
- `transportPhase`

避免继续使用一个含义重叠的 `variables.status`。

## 5. 模型定义与实例运行态

### 5.1 `model.json`
`model.json` 只描述模型定义，不描述某个实例当前值。

应包含：

- 字段定义
- 规则与能力定义
- 状态机定义
- 目标与决策策略定义
- 记忆槽位定义
- 计划结构定义

### 5.2 实例文件
实例文件描述某个具体 agent 的运行态。

推荐包含：

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

### 5.3 `bindings`
`bindings` 只出现在实例层，用于描述外部接线方式。

例如：

- `variables.temperature = 1650`
- `bindings.temperature.source = "plc_line_a"`

这样可以清晰区分：

- `variables`: 当前内部值
- `bindings`: 数据从哪里来、如何映射

## 6. 必选项与条件必选项

### 6.1 最小必选项

- `$schema`
- `metadata.name`
- `metadata.title`

同时模型至少具备以下之一：

- `attributes`
- `variables`
- `services`
- `goals`

### 6.2 条件必选项

- 存在 `derivedProperties` 时，其依赖字段必须存在
- 存在 `transitions` 时，必须存在 `states`
- 存在 `decisionPolicies` 时，其引用的 `goals / memory / plans` 必须存在
- 存在 `alarms / behaviors / schedules` 时，其动作引用的事件、服务或动作必须存在

## 7. 两类典型 agent

### 7.1 实体型 agent
例如钢包、天车、设备单元。

特点：

- 具身信息重
- `reflex` 重
- `cortex` 轻

典型能力：

- 安全检查
- 状态流转
- 局部异常处理
- 简单计划调整

### 7.2 调度型 agent
例如产线调度、工艺协调、资源编排。

特点：

- 具身信息轻
- `reflex` 适中
- `cortex` 重

典型能力：

- 多目标权衡
- 冲突消解
- 中短期计划生成
- 多实体协作决策

## 8. 实现建议

### 8.1 迁移顺序

1. 先收紧旧 schema 的职责边界
2. 再最小化引入 `goals / decisionPolicies`
3. 最后补充 `memory / plans`

### 8.2 校验优先级
优先实现以下校验：

- 引用完整性校验
- `functions` 纯函数校验
- 状态机一致性校验
- `cortex` 引用校验
- 模型与实例职责边界校验

## 9. 一句话总结
Agent Studio 的 v2 方向不是把“物模型”替换成“智能体模型”，而是把物模型纳入统一的 agent 抽象中，在保持配置扁平的前提下，让同一份 schema 同时覆盖具身、`reflex` 和 `cortex`。
