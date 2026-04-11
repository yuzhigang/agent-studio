# Agent Studio 数据库设计文档

## 设计目标

本版数据库设计服务于 Agent Studio v2 schema。v2 的核心变化是：

- 统一抽象以 agent 为核心
- `model.json` 保持扁平顶层结构
- 模型层显式支持 `goals / decisionPolicies / memory / plans`
- 实例层显式拆分 `variables` 与 `bindings`
- 实例层增加 `memory / activeGoals / currentPlan`

数据库设计必须同时支持：

- 模型文件的完整持久化
- 实例运行态的高频读写
- 变量值查询与索引
- 低频认知上下文的 JSON 化存储
- 告警、事件、日志的时序检索

## 设计原则

1. **模型存储最小化**：模型数量少，配置复杂，数据库存元数据，完整模型定义存文件。
2. **实例运行态分层**：高频变化的变量值单独存储，低频变化的认知上下文优先放 JSON。
3. **接线方式实例化**：`bindings` 属于实例层，不进入模型元数据表。
4. **认知上下文轻量化**：`memory / activeGoals / currentPlan` 初期放实例主表 JSON，后续按查询需求再拆。
5. **时序数据独立化**：告警、事件、日志独立成表，便于生命周期管理和归档。

---

## 文件系统与数据库分工

### 模型文件
完整模型定义继续存文件，例如：

- `/models/ladle.json`
- `/models/crane.json`
- `/models/scheduler.json`

文件内容包含完整的 v2 schema：

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
- `goals`
- `decisionPolicies`
- `memory`
- `plans`

### 数据库存储
数据库只存：

- 模型元数据和文件路径
- 实例主信息与低频 JSON 上下文
- 高频变量值
- 告警、事件、日志

---

## 表结构

### 1. `models`（模型元数据表）

存储模型基本信息和文件关联。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 模型标识，如 `ladle` |
| name | VARCHAR(64) | NOT NULL, UNIQUE | 模型名称 |
| title | VARCHAR(128) | NOT NULL | 显示标题 |
| file_path | VARCHAR(500) | NOT NULL | 模型文件路径 |
| group_name | VARCHAR(64) | INDEX | 分组 |
| creator | VARCHAR(64) | - | 创建者 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |
| version | VARCHAR(16) | NOT NULL | 模型版本号 |
| is_active | BOOLEAN | DEFAULT TRUE, INDEX | 是否启用 |

**说明**

- `file_path` 指向完整的 `model.json`
- 数据库不拆存 `goals / decisionPolicies / memory / plans`
- 这些结构仍以文件为准，由应用层读取、缓存和校验

**索引**

- `PRIMARY KEY (id)`
- `UNIQUE KEY uk_name (name)`
- `KEY idx_group (group_name)`
- `KEY idx_active (is_active)`

---

### 2. `instances`（实例主表）

存储实例核心信息、低频配置和认知上下文。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 实例标识，如 `ladle_001` |
| model_id | VARCHAR(64) | FK, INDEX | 关联 `models.id` |
| current_state | VARCHAR(64) | NOT NULL, INDEX | 当前 `reflex` 状态 |
| name | VARCHAR(128) | NOT NULL | 实例名称 |
| title | VARCHAR(128) | - | 显示标题 |
| description | TEXT | - | 描述 |
| attributes | JSON | - | 实例属性值 |
| bindings | JSON | - | 实例接线配置 |
| memory | JSON | - | 结构化运行记忆 |
| active_goals | JSON | - | 当前激活目标列表 |
| current_plan | JSON | - | 当前计划摘要 |
| extensions | JSON | - | 额外运行时扩展 |
| version | VARCHAR(16) | NOT NULL | 实例数据版本 |
| creator | VARCHAR(64) | - | 创建者 |
| created_at | DATETIME | NOT NULL, INDEX | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |
| is_deleted | BOOLEAN | DEFAULT FALSE, INDEX | 软删除标记 |

**设计说明**

- `attributes` 存实例属性最终值
- `bindings` 存实例数据源接线方式
- `memory / active_goals / current_plan` 作为低频上下文存 JSON
- 高频 `variables` 不直接放在 `instances` 表，而是进入 `instance_variables`

**`bindings` JSON 示例**

```json
{
  "temperature": {
    "source": "plc_line_a",
    "path": "ns=2;s=Ladle01.Temp",
    "selector": "$.temperature",
    "transform": "Math.round(value)"
  },
  "currentLocation": {
    "source": "factory_mqtt",
    "topic": "position/ladle/001",
    "selector": "$.position.zone",
    "transform": "value.toLowerCase().replace(/\\s/g, '_')"
  }
}
```

**`memory` JSON 示例**

```json
{
  "currentAssignment": {
    "taskId": "task_20260411_001",
    "destination": "caster_2",
    "deadline": "2026-04-11T10:30:00Z"
  },
  "lastDecision": {
    "mode": "cortex",
    "summary": "优先送达 caster_2"
  }
}
```

**`current_plan` JSON 示例**

```json
{
  "id": "plan_20260411_001",
  "planType": "deliveryAdjustment",
  "status": "ready",
  "steps": [
    {
      "service": "assignTargetLocation",
      "args": {
        "targetLocation": "caster_2"
      }
    },
    {
      "service": "moveTo",
      "args": {
        "targetLocation": "caster_2"
      }
    }
  ]
}
```

**索引**

- `PRIMARY KEY (id)`
- `KEY idx_model (model_id)`
- `KEY idx_state (current_state)`
- `KEY idx_created (created_at)`
- `KEY idx_deleted (is_deleted)`

---

### 3. `instance_variables`（实例变量值表）

变量值是核心业务数据，单独存储以支持查询、排序和索引。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 自增 ID |
| instance_id | VARCHAR(64) | FK, NOT NULL | 关联 `instances.id` |
| name | VARCHAR(64) | NOT NULL | 变量名 |
| value | VARCHAR(255) | INDEX | 变量值，统一字符串持久化 |
| value_type | VARCHAR(16) | - | 实际类型，如 `number/string/boolean` |
| updated_at | DATETIME | NOT NULL | 更新时间 |

**设计说明**

- `variables` 的权威运行态在本表
- 接口层返回实例详情时，可按需把本表变量聚合回 JSON
- 需要过滤、排序、比较的变量尽量走本表查询

**联合索引**

- `PRIMARY KEY (id)`
- `UNIQUE KEY uk_instance_var (instance_id, name)`
- `KEY idx_value (value)`
- `KEY idx_instance_updated (instance_id, updated_at)`

---

### 4. `instance_alarms`（实例告警表）

告警有生命周期状态，需要独立表支持状态管理。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 告警 ID |
| instance_id | VARCHAR(64) | FK, NOT NULL, INDEX | 关联 `instances.id` |
| rule_id | VARCHAR(128) | NOT NULL | 触发规则名或告警定义名 |
| severity | VARCHAR(16) | NOT NULL, INDEX | 级别，如 `warning/critical` |
| level | INT | NOT NULL, INDEX | 告警等级 |
| status | VARCHAR(16) | NOT NULL, INDEX | 状态，如 `triggered/confirmed/cleared` |
| message | VARCHAR(500) | NOT NULL | 告警消息 |
| payload | JSON | - | 上下文数据 |
| triggered_at | DATETIME | NOT NULL, INDEX | 触发时间 |
| confirmed_at | DATETIME | - | 确认时间 |
| confirmed_by | VARCHAR(64) | - | 确认人 |
| cleared_at | DATETIME | INDEX | 清除时间 |
| cleared_by | VARCHAR(64) | - | 清除人 |
| created_at | DATETIME | NOT NULL | 创建时间 |

**索引**

- `PRIMARY KEY (id)`
- `KEY idx_instance (instance_id)`
- `KEY idx_status (status)`
- `KEY idx_level (level)`
- `KEY idx_severity (severity)`
- `KEY idx_triggered (triggered_at)`
- `KEY idx_instance_status (instance_id, status)`

---

### 5. `instance_events`（实例事件表）

事件是只增不改的时序数据。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 事件 ID |
| instance_id | VARCHAR(64) | FK, NOT NULL, INDEX | 关联 `instances.id` |
| event_type | VARCHAR(64) | NOT NULL, INDEX | 事件类型 |
| timestamp | DATETIME | NOT NULL, INDEX | 发生时间 |
| payload | JSON | - | 事件数据 |
| created_at | DATETIME | NOT NULL | 创建时间 |

**payload 示例**

```json
{
  "from": "receiving",
  "to": "full",
  "trigger": "beginLoad"
}
```

```json
{
  "service": "moveTo",
  "params": {
    "targetLocation": "caster_2"
  },
  "result": "success"
}
```

```json
{
  "planId": "plan_20260411_001",
  "mode": "cortex",
  "reason": "routeConflictDetected"
}
```

**索引**

- `PRIMARY KEY (id)`
- `KEY idx_instance (instance_id)`
- `KEY idx_type (event_type)`
- `KEY idx_timestamp (timestamp)`
- `KEY idx_instance_time (instance_id, timestamp)`

---

### 6. `instance_logs`（可选日志表）

若需要持久化日志，建议独立表或外部日志系统。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 自增 ID |
| instance_id | VARCHAR(64) | FK, NOT NULL, INDEX | 关联 `instances.id` |
| timestamp | DATETIME | NOT NULL, INDEX | 时间戳 |
| level | VARCHAR(16) | INDEX | 级别 |
| message | TEXT | - | 日志内容 |
| source | VARCHAR(32) | - | 来源，如 `state-machine/service/schedule/rule/cortex` |
| context | JSON | - | 上下文 |

---

## v2 结构映射

### 模型文件结构

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

### 实例文件结构

```json
{
  "$schema": "https://agent-studio.io/schema/v2/instance",
  "id": "ladle_001",
  "modelId": "ladle",
  "state": "full",
  "metadata": {},
  "attributes": {},
  "variables": {},
  "bindings": {},
  "memory": {},
  "activeGoals": [],
  "currentPlan": {},
  "extensions": {}
}
```

---

## 存储策略建议

### 应优先单独成表的内容

- 高频变化、需要过滤排序的 `variables`
- 告警生命周期数据
- 事件时间线
- 日志

### 应优先放 JSON 的内容

- `attributes`
- `bindings`
- `memory`
- `active_goals`
- `current_plan`
- `extensions`

### 未来可拆分的内容

如果后续出现下列场景，可以再考虑单独拆表：

- 需要按目标状态统计 `activeGoals`
- 需要检索 `currentPlan.steps.service`
- 需要分析长期 `memory` 历史

在 v2 初期，这些内容仍以 JSON 为主更合适。

---

## 结论

Agent Studio v2 的数据库设计遵循一个简单原则：

- 模型定义继续文件化
- 实例运行态分层存储
- 高频变量值独立化
- 低频认知上下文 JSON 化

这样可以在不增加存储复杂度的前提下，让同一套系统同时承载具身 agent、反应式 agent 和带有限 `cortex` 能力的 hybrid agent。
