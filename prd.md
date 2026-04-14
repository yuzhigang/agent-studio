# Agent Studio v2 产品设计文档

## 1. 产品概述

Agent Studio 是一个面向工业场景的智能体建模平台。v2 的核心目标是：以统一的 schema 覆盖从"具备物理状态的设备实体"到"具备推理决策能力的调度协调者"这一完整能力谱系。

### 1.1 核心立场

不再把"物模型"和"智能体模型"看成两套平行体系：

- **物模型**是 agent 的**具身部分**
- **reflex** 是 agent 的**快速响应系统**
- **cortex** 是 agent 的**慢速决策系统**

这意味着：

- 钢包、天车、设备单元是 agent
- 产线调度、工艺协调、资源编排也是 agent
- 它们使用同一份顶层 schema，只是能力重心不同

### 1.2 概念分层，配置扁平

`embodiment / reflex / cortex` 是方法论分层，不是配置文件中的独立嵌套块。配置作者面对的始终是扁平的顶层键，降低配置成本，保持向后兼容。

---

## 2. 顶层结构

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

各字段按方法论分层归属如下：

| 层     | 字段                                                                                            |
| ------ | ----------------------------------------------------------------------------------------------- |
| 具身   | `attributes` `variables` `derivedProperties`                                                    |
| reflex | `rules` `functions` `services` `states` `transitions` `behaviors` `events` `alarms` `schedules` |
| cortex | `goals` `decisionPolicies` `memory` `plans`                                                     |

---

## 3. 具身层

### 3.1 `attributes`

静态配置边界，描述 agent 实例的物理特征或不变参数。不随运行而改变。
可通过 `x-audit` 标记该属性变更是否需要写入审计历史。

```json
"capacity":       { "type": "number", "x-unit": "ton", "x-audit": true },
"maxTemperature": { "type": "number", "x-unit": "℃", "x-audit": true }
```

### 3.2 `variables`

运行时状态，描述 agent 当前的动态值。每次执行 service、响应 behavior 或执行定时任务，均可修改 variables。
可通过 `x-audit` 标记该变量变更是否需要写入审计历史。

```json
"steelAmount":    { "type": "number", "default": 0, "x-audit": true },
"temperature":    { "type": "number", "default": 25, "x-audit": true }
```

variable的变化是由 `bindings` 来驱动的。`bindings` 只出现在实例层，用于描述外部接线方式。

例如：

- `variables.temperature = 1650`
- `bindings.temperature.source = "plc_line_a"`

这样可以清晰区分：

- `variables`: 当前内部值
- `bindings`: 数据从哪里来、如何映射

### 3.3 `derivedProperties`

基于 `attributes` 和 `variables` 的计算视图，不可直接写入。需声明 `x-formula` 和 `x-dependOn`。
可通过 `x-audit` 标记该派生结果变化是否需要写入审计历史。

```json
"fillRate": {
  "type": "number",
  "x-audit": true,
  "x-formula": "this.variables.steelAmount / this.attributes.capacity * 100",
  "x-dependOn": ["steelAmount", "capacity"]
}
```

---

## 4. reflex 层

### 4.1 `rules`

硬约束、安全边界、权限校验。只放确定性判断，不放目标优化。

支持三种违规响应：

- `action: "reject"` — 拒绝执行，返回错误
- `action: "warn"` — 允许继续，附带告警
- `action: "override"` — 强制执行（需审计）

```json
"capacityLimit": {
  "condition": "this.variables.steelAmount <= this.attributes.capacity",
  "onViolation": { "action": "reject", "error": { "code": "CAPACITY_EXCEEDED" } }
}
```

适合放进 `rules`：容量上限、温度安全范围、权限角色、机械门禁、状态前置条件。
不适合放进 `rules`：吞吐最大化、等待时间最小化、订单优先级——这些属于 `goals`。

### 4.2 `functions`

**纯计算函数**，只读上下文，不写任何状态。用于查询、推算、模拟评估。

凡是会修改 `variables / attributes / memory / state` 的逻辑，一律不进 `functions`，应进入 `services`、`behaviors` 或计划执行器。

### 4.3 `services`

Agent 对外暴露的**统一动作入口**（Command 面）。可被以下调用方使用：

- 人工操作
- 外部系统（MES、WMS、调度系统）
- reflex 触发
- cortex 计划落地

每个 service 支持：

- `rules.pre` / `rules.post`：执行前后的规则检查
- `permissions.roles`：角色权限约束

```json
"pour": {
  "rules": {
    "pre": [{ "rule": "hasSteelBeforePour" }, { "rule": "minPourTemperature" }]
  },
  "permissions": { "roles": ["caster_operator", "system"] }
}
```

### 4.4 `states` 与 `transitions`

**`states`** 只定义状态的描述性元数据：

```json
"empty": {
  "title": "空包",
  "group": "loadState",
  "initialState": true
}
```

**`transitions`** 只定义状态机拓扑：from / to / trigger。不包含任何副作用（actions）。

```json
"emptyToReceiving": {
  "from": "empty",
  "to": "receiving",
  "trigger": { "type": "event", "name": "beginLoad" }
}
```

`state` 的每次变更（包括任意 `from -> to` 迁移）都必须加入审计历史，该要求为强制项，不受 `x-audit` 开关影响。

所有副作用（进入状态后做什么、迁移时打什么日志）统一移入 `behaviors`，通过 `stateEnter / stateExit / transition` trigger 类型实现。这样实现**单一职责**：想知道"某个状态变化会产生什么副作用"，只看 `behaviors`。

Trigger 支持的类型：

- `type: "event"` — 收到指定名称的事件
- `type: "condition"` — 轮询窗口内条件成立
- `type: "timeout"` — 等待指定时长后触发

### 4.5 `behaviors`

`behaviors` 是 agent 所有**副作用的唯一归宿**。

涵盖以下来源的副作用：

1. 收到外部事件时的响应（原有用途）
2. 进入/退出某个 FSM 状态时的动作（从 `states.actions` 迁入）
3. 某个 transition 触发时的附加逻辑（从 `transitions.actions` 迁入）

#### Trigger 类型

| `type`       | 含义                             |
| ------------ | -------------------------------- |
| `event`      | 收到指定名称的事件（外部或自发） |
| `stateEnter` | 进入指定 FSM 状态                |
| `stateExit`  | 退出指定 FSM 状态                |
| `transition` | 指定迁移被触发                   |

```json
"onEnterEmpty_reset": {
  "trigger": { "type": "stateEnter", "state": "empty" },
  "priority": 10,
  "actions": [{ "type": "runScript", "script": "this.variables.steelAmount = 0\n..." }]
},
"onEnterEmpty_notify": {
  "trigger": { "type": "stateEnter", "state": "empty" },
  "priority": 20,
  "after": "onEnterEmpty_reset",
  "actions": [{ "type": "triggerEvent", "name": "ladleStatusChanged" }]
},
"captureConverterTarget": {
  "trigger": { "type": "event", "name": "beginLoad", "when": "payload.converterId != null" },
  "actions": [{ "type": "runScript", "script": "this.variables.targetLocation = ..." }]
}
```

#### 执行顺序

同一 trigger 下存在多个 behavior 时，执行顺序由以下两个字段控制（二选一）：

- `priority`（数字，升序执行）：适合独立行为之间的粗粒度排序
- `after`（引用另一 behavior 名称）：适合有明确依赖关系的场景

两者可并用，`after` 的优先级高于 `priority`。

### 4.6 `events`

**`events` 定义本 agent 自身能发出去的事件契约**（出站发布方视角）。

每条事件定义包含：

- `title`：事件描述
- `payload`：载荷字段 schema

```json
"ladleLoaded": {
  "title": "钢包接钢完成",
  "payload": {
    "ladleId":    { "type": "string" },
    "steelAmount":{ "type": "number" },
    "steelGrade": { "type": "string" },
    "temperature":{ "type": "number" }
  }
}
```

`behaviors` 中监听的外部事件（即其他 agent 发出的事件），其 payload schema 由**全局事件注册表**提供，无需在本地重复声明。`behaviors.trigger` 只引用事件名称即可。

### 4.7 `alarms`

告警生命周期定义，支持触发条件和清除条件双向声明。

```json
"alarms": {
 "highFillRate.high": {
      "category": "highFillRate",
      "title": "高装载率预警",
      "trigger": {
          "type": "condition",
          "window": {
              "type": "time-sliding",
              "duration": 300
          },
          "condition": "this.variables.steelAmount >= this.attributes.capacity * 0.95"
      },
      "clear": {
          "type": "condition",
          "window": {
              "type": "time-sliding",
              "duration": 300
          },
          "condition": "this.variables.steelAmount < this.attributes.capacity * 0.95"
      },
      "severity": "warning",
      "level": 1,
      "triggerMessage": "钢包装载率达到 {fillRate}% ，移动和倾倒时请谨慎操作",
      "clearMessage": "钢包装载率已恢复到安全范围"
  }
}
```

### 4.8 `schedules`

定时触发的检查和动作。支持 cron 表达式， `condition`（仅在条件满足时执行）和 `onFailure`（检查未通过时的后续动作）：

```json
"checkTemperature": {
  "cron": "*/5 * * * *",
  "condition": "this.variables.steelAmount > 0",
  "actions": [{ "type": "runScript", "script": "..." }],
  "onFailure": [{ "type": "triggerAlarm", "alarm": "temperatureTooLow.warning" }]
}
```

---

## 5. 输入驱动模型

### 5.1 驱动因素分类

驱动 agent 状态更新的外部因素可归结为六类：

| 分类     | 来源                  | 本质                                 |
| -------- | --------------------- | ------------------------------------ |
| 遥测流   | PLC、IoT 传感器、RTLS | 物理世界连续变化的反映，是事实       |
| 操作命令 | 操作员、上位系统      | 发向 agent 的意图性请求，可被拒绝    |
| 领域事件 | 其他 agent、系统      | 已发生的事实通知，不可拒绝，只能响应 |
| 调度指令 | 调度系统、MES         | 任务分配，需判断是否能接受及如何执行 |
| 异常信号 | 监控系统、检测模块    | 偏差/冲突检测结果，总是需要决策      |
| 时间触发 | 系统时钟              | 时间本身流逝，触发周期性检查         |

### 5.2 三条输入通道

以上六类因素通过三条通道进入 agent：

```
操作命令 ──────────────→  services   (RPC 调用，经规则检查)
领域事件 / 调度指令 ──→  behaviors  (事件订阅，触发副作用)
时间触发 ──────────────→  schedules  (定时任务)

遥测流：通过实例层 bindings 绑定到 variables，
        由运行时引擎在变量更新后自动触发：
        派生属性重算 → 报警条件评估
```

### 5.3 路由逻辑

```
input 到达
│
├─ type = COMMAND (service 调用)
│   ├─ 检查 allowedStates（当前 FSM 状态是否允许）
│   ├─ 执行 pre-rules（违反则拒绝）
│   ├─ 执行 service 脚本
│   ├─ 执行 post-rules（违反则 warn 或 rollback）
│   └─ 可能触发 FSM transition → 触发 stateEnter/stateExit behaviors
│
├─ type = EVENT (behaviors 响应)
│   ├─ 匹配所有 trigger.type == "event" && name 相符的 behaviors
│   ├─ 按 priority / after 排序执行
│   └─ 可能修改 variables → 触发报警重评估
│
└─ type = SCHEDULE (定时执行)
    ├─ 评估 condition（不满足则跳过）
    ├─ 执行 actions
    └─ 失败时执行 onFailure
```

### 5.4 反射与皮层的路由决策

在 `decisionPolicies` 中声明以下内容，决定某类输入由 reflex 还是 cortex 处理：

```json
"defaultOperationalMode": {
  "preferredMode": "reflex",
  "reflexCapabilities": {
    "canInvokeServices": ["moveTo", "loadSteel", "pour"],
    "canFireTransitions": true
  },
  "cortexCapabilities": {
    "tools": ["assignTargetLocation", "moveTo"],
    "maxPlanSteps": 10,
    "decisionTimeoutMs": 5000,
    "timeoutFallback": "freeze_and_alert"
  },
  "escalateWhen": [
    { "type": "goalConflict", "goals": ["safeHandling", "timelyDelivery"] },
    { "type": "event", "name": "routeConflictDetected" },
    { "type": "event", "name": "deliveryDelayDetected" }
  ]
}
```

`timeoutFallback` 定义皮层超时后 reflex 的降级行为，是安全关键字段。

---

## 6. cortex 层

### 6.1 `goals`

Agent 追求的目标，包含优先级和成功条件：

```json
"safeHandling": {
  "priority": 100,
  "successCondition": "this.variables.steelAmount <= this.attributes.capacity && this.variables.temperature <= this.attributes.maxTemperature"
},
"timelyDelivery": {
  "priority": 80,
  "successCondition": "this.variables.targetLocation == '' || this.variables.currentLocation == this.variables.targetLocation"
}
```

### 6.2 `memory`

Cortex 决策所需的结构化上下文槽位。由 cortex 读写，reflex 不直接修改。

```json
"currentAssignment":    { "type": "object",  "description": "当前运输或倾倒任务摘要" },
"recentAbnormalEvents": { "type": "array",   "maxItems": 20 },
"lastDecision":         { "type": "object",  "description": "最近一次 cortex 决策摘要与原因" }
```

### 6.3 `plans`

Cortex 输出的结构化计划模板。`allowedServices` 是 **安全关键字段**，约束 cortex 只能生成操作特定 service 的步骤，防止计划越界。

```json
"deliveryAdjustment": {
  "title": "配送调整计划",
  "stepSchema": {
    "service": { "type": "string" },
    "args":    { "type": "object" }
  },
  "allowedServices": ["assignTargetLocation", "moveTo"],
  "successCondition": "this.variables.currentLocation == this.variables.targetLocation"
}
```

**计划执行生命周期**（待实现）：

```
created → executing → step_n
                    ├─ step_failed → retrying / aborted
                    ├─ interrupted (新 escalateWhen 信号到来)
                    └─ succeeded
```

---

## 7. 全局事件注册表

每个 agent 的 `events` 字段声明本体发布的事件契约。平台层维护一个**全局事件注册表**，聚合所有 agent 的事件定义：

```
EventRegistry
├── Converter.beginLoad       { payload: { converterId, heatNumber } }
├── Ladle.ladleLoaded         { payload: { ladleId, steelAmount, steelGrade, temperature } }
├── Ladle.ladleEmptied        { payload: { ladleId, usageCount } }
├── DispatchSystem.dispatchAssigned   { payload: { destinationType, destinationId, taskId } }
└── TrafficController.routeConflictDetected { payload: { conflictId, severity } }
```

`behaviors` 中通过事件名引用，运行时由注册表解析 payload schema，无需在各 agent 模型中重复声明。

---

## 8. 关系建模（links）

Agent 不是孤立对象，而是嵌入在对象图中的节点。`links` 描述 agent 与其他类型实体之间的有类型关系（待实现）：

```json
"links": {
  "assignedCaster": {
    "title": "绑定铸机",
    "targetType": "ContinuousCaster",
    "cardinality": "0..1"
  },
  "transportCrane": {
    "title": "当前运输天车",
    "targetType": "Crane",
    "cardinality": "0..1"
  },
  "currentHeat": {
    "title": "当前炉次记录",
    "targetType": "HeatRecord",
    "cardinality": "0..1"
  }
}
```

`links` 是多智能体协同的基础：cortex 通过图遍历感知"哪个天车可运我"、"同一炉次下有哪些钢包"，而不是通过字符串变量猜测。

---

## 9. 两类典型智能体

### 9.1 实体型 agent（如钢包、天车）

| 维度   | 特点                         |
| ------ | ---------------------------- |
| 具身   | 重（物理属性丰富）           |
| reflex | 重（安全规则多，状态机密集） |
| cortex | 轻（仅处理冲突和异常升级）   |

典型能力：安全检查、状态流转、局部异常处理、简单计划调整。

### 9.2 调度型 agent（如产线调度、工艺协调）

| 维度   | 特点                                 |
| ------ | ------------------------------------ |
| 具身   | 轻（无物理约束）                     |
| reflex | 适中（流程规则、权限）               |
| cortex | 重（多目标权衡、冲突消解、计划生成） |

典型能力：多目标权衡、冲突消解、中短期计划生成、多实体协作决策。

---

## 10. 字段职责约束

| 约束                               | 说明                                               |
| ---------------------------------- | -------------------------------------------------- |
| `functions` 必须纯                 | 只读，不写 variables / attributes / memory / state |
| `transitions` 无 actions           | 只有 from / to / trigger，副作用全部进 behaviors   |
| `states` 无 actions                | 只有描述性元数据，副作用全部进 behaviors           |
| `state` 变更必须审计               | 任意 `from -> to` 迁移都必须写入审计历史，不可关闭 |
| `rules` 只有硬约束                 | 不放目标优化逻辑                                   |
| `cortex` 不绕过 rules              | cortex 决定"做什么"，不能绕过安全边界              |
| `events` 仅声明出站事件            | 外部事件 schema 由全局注册表管理                   |
| `allowedServices` 约束 cortex 边界 | plans 只能引用白名单内的 service                   |

---

## 11. 模型与实例的职责边界

### `model.json` 只描述定义

- 字段类型与约束
- 规则与能力契约
- 状态机拓扑
- 目标与决策策略
- 记忆槽位结构
- 计划模板

### 实例文件描述运行态

```json
{
  "id": "ladle-001",
  "modelId": "ladle",
  "state": "full",
  "attributes": { "capacity": 200 },
  "variables": { "steelAmount": 185, "temperature": 1610 },
  "bindings": {
    "temperature": { "source": "plc_line_a", "path": "T_LADLE_01" }
  },
  "memory": {
    "currentAssignment": { "taskId": "T-2026-0413-001", "deadline": "..." }
  },
  "activeGoals": ["safeHandling", "timelyDelivery"],
  "currentPlan": null
}
```

`bindings` 只在实例层出现，描述外部数据源与 variables 的接线关系，不进入模型定义。

---

## 12. 校验优先级

| 优先级 | 校验项                                                                      |
| ------ | --------------------------------------------------------------------------- |
| P0     | 引用完整性（behaviors 引用的 event/state/transition 必须存在）              |
| P0     | `functions` 纯函数校验（不含写操作）                                        |
| P0     | `transitions` 无 actions 校验                                               |
| P1     | 状态机一致性（所有 transition 的 from/to 必须在 states 中定义）             |
| P1     | cortex 引用校验（decisionPolicies 引用的 goals / memory / plans 必须存在）  |
| P2     | `allowedServices` 白名单校验（plans 引用的 service 必须在 services 中定义） |
| P2     | 模型与实例职责边界（实例文件不含 rules / transitions 等模型专属字段）       |
