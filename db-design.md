# Agent Studio 数据库设计文档

## 设计原则

1. **模型存储最小化**：Model 数量少（<500），配置复杂，数据库存储元数据，完整配置存文件
2. **实例数据核心化**：实例数量大，需要数据库支持，配置类字段合并为 JSON
3. **变量值独立化**：变量值是核心业务数据，单独成表支持查询、排序和索引
4. **运行时数据分离**：告警、事件、日志单独成表，支持时序查询和生命周期管理

---

## 表结构

### 1. models（模型元数据表）

存储模型基本信息和文件关联。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 模型标识 (如: ladle) |
| name | VARCHAR(64) | NOT NULL, UNIQUE | 模型名称 |
| title | VARCHAR(128) | NOT NULL | 显示标题 |
| file_path | VARCHAR(500) | NOT NULL | model.json 文件路径 |
| group_name | VARCHAR(64) | INDEX | 分组 (如: logistics) |
| creator | VARCHAR(64) | - | 创建者 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |
| version | VARCHAR(16) | NOT NULL | 模型版本号 |
| is_active | BOOLEAN | DEFAULT TRUE, INDEX | 是否启用 |

**说明**：`file_path` 指向 `/models/ladle.json` 等实际配置文件，包含完整的 attributes、variables、rules、states、transitions、services、alarms、schedules 定义。

**索引**：
- `PRIMARY KEY (id)`
- `UNIQUE KEY uk_name (name)`
- `KEY idx_group (group_name)`
- `KEY idx_active (is_active)`

---

### 2. instances（实例主表）

存储实例核心信息，配置类数据存 JSON。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 实例标识 (如: ladle_001) |
| model_id | VARCHAR(64) | FK, INDEX | 关联 models.id |
| current_state | VARCHAR(64) | NOT NULL, INDEX | 当前状态 |
| name | VARCHAR(128) | NOT NULL | 实例名称 |
| title | VARCHAR(128) | - | 显示标题 |
| description | TEXT | - | 描述 |
| attributes | JSON | - | 属性值 (capacity, maxTemperature 等) |
| extensions | JSON | - | 扩展数据 (maintenance, lifecycle, ops) |
| version | VARCHAR(16) | NOT NULL | 实例数据版本 |
| creator | VARCHAR(64) | - | 创建者 |
| created_at | DATETIME | NOT NULL, INDEX | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |
| is_deleted | BOOLEAN | DEFAULT FALSE, INDEX | 软删除标记 |

**attributes JSON 示例**：
```json
{
  "capacity": 200,
  "maxTemperature": 1800,
  "insulationDuration": 120
}
```

**extensions JSON 示例**：
```json
{
  "maintenance": {
    "usageCount": 0,
    "lastMaintenanceTime": null
  },
  "lifecycle": {
    "totalPours": 0,
    "totalSteelHandled": 0
  },
  "ops": {
    "lastCheckTime": null
  }
}
```

**索引**：
- `PRIMARY KEY (id)`
- `KEY idx_model (model_id)`
- `KEY idx_state (current_state)`
- `KEY idx_created (created_at)`
- `KEY idx_deleted (is_deleted)`

---

### 3. instance_variables（实例变量值表）

变量值是核心业务数据，需要单独存储以支持查询、排序和索引。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 自增ID |
| instance_id | VARCHAR(64) | FK, NOT NULL | 关联 instances.id |
| name | VARCHAR(64) | NOT NULL | 变量名 |
| value | VARCHAR(255) | INDEX | 变量值 (统一字符串存储) |
| value_type | VARCHAR(16) | - | 实际类型 (number/string/boolean) |
| updated_at | DATETIME | NOT NULL | 更新时间 |

**联合索引**：
- `PRIMARY KEY (id)`
- `UNIQUE KEY uk_instance_var (instance_id, name)` - 一个实例的变量名不重复
- `KEY idx_value (value)` - 支持变量值查询

**说明**：
- 数值类型变量存储为字符串，应用层转换
- 需要查询的变量（如 steelAmount > 100）在此表操作

---

### 4. instance_alarms（实例告警表）

告警有生命周期状态，需要独立表支持状态管理。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 告警ID |
| instance_id | VARCHAR(64) | FK, NOT NULL, INDEX | 关联 instances.id |
| rule_id | VARCHAR(128) | NOT NULL | 触发规则名 (如: temperatureExceeded) |
| severity | VARCHAR(16) | NOT NULL, INDEX | 级别 (warning/critical) |
| level | INT | NOT NULL, INDEX | 告警等级 (1-5) |
| status | VARCHAR(16) | NOT NULL, INDEX | 状态 (triggered/confirmed/cleared) |
| message | VARCHAR(500) | NOT NULL | 告警消息 |
| payload | JSON | - | 上下文数据 (温度值、阈值等) |
| triggered_at | DATETIME | NOT NULL, INDEX | 触发时间 |
| confirmed_at | DATETIME | - | 确认时间 |
| confirmed_by | VARCHAR(64) | - | 确认人 |
| cleared_at | DATETIME | INDEX | 清除时间 |
| cleared_by | VARCHAR(64) | - | 清除人 |
| created_at | DATETIME | NOT NULL | 创建时间 |

**状态流转**：
```
triggered → confirmed → cleared
     ↓           ↓
   (自动清除)   (人工确认)
```

**payload JSON 示例**：
```json
{
  "variable": "temperature",
  "currentValue": 1850,
  "threshold": 1800,
  "unit": "℃"
}
```

**索引**：
- `PRIMARY KEY (id)`
- `KEY idx_instance (instance_id)`
- `KEY idx_status (status)`
- `KEY idx_level (level)`
- `KEY idx_severity (severity)`
- `KEY idx_triggered (triggered_at)`
- `KEY idx_cleared (cleared_at)`
- `KEY idx_instance_status (instance_id, status)` - 查询实例活跃告警

---

### 5. instance_events（实例事件表）

事件是只增不改的时序数据，结构简单。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | VARCHAR(64) | PK | 事件ID |
| instance_id | VARCHAR(64) | FK, NOT NULL, INDEX | 关联 instances.id |
| event_type | VARCHAR(64) | NOT NULL, INDEX | 类型 (state-change/service-call/alarm-trigger/variable-change) |
| timestamp | DATETIME | NOT NULL, INDEX | 发生时间 |
| payload | JSON | - | 事件数据 |
| created_at | DATETIME | NOT NULL | 创建时间 |

**payload JSON 示例**：
```json
// state-change
{ "from": "empty", "to": "receiving", "trigger": "beginLoad" }

// service-call  
{ "service": "loadSteel", "params": { "weight": 150 }, "result": "success" }

// variable-change
{ "variable": "temperature", "old": 1500, "new": 1520 }

// alarm-trigger
{ "alarmId": "alarm_ladle_001_001", "ruleId": "temperatureExceeded" }
```

**索引**：
- `PRIMARY KEY (id)`
- `KEY idx_instance (instance_id)`
- `KEY idx_type (event_type)`
- `KEY idx_timestamp (timestamp)`
- `KEY idx_instance_time (instance_id, timestamp)` - 查询实例时间线

---

### 6. instance_logs（可选，实例日志表）

如果日志需要持久化，建议单独表（或送外部日志系统如 ELK）。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 自增ID |
| instance_id | VARCHAR(64) | FK, NOT NULL, INDEX | 关联 instances.id |
| timestamp | DATETIME | NOT NULL, INDEX | 时间戳 |
| level | VARCHAR(16) | INDEX | 级别 (debug/info/warn/error) |
| message | TEXT | - | 日志内容 |
| source | VARCHAR(32) | - | 来源 (state-machine/service/schedule/rule/system) |
| context | JSON | - | 上下文 (文件名、行号等) |

**context JSON 示例**：
```json
{
  "file": "loadSteel.py",
  "line": 42,
  "function": "execute",
  "traceId": "trace_001"
}
```

**索引**：
- `PRIMARY KEY (id)`
- `KEY idx_instance (instance_id)`
- `KEY idx_level (level)`
- `KEY idx_timestamp (timestamp)`

---

## ER 关系图

```
┌─────────────────────────────────────────────────────────────────────────┐
│  File System                                                            │
│  /models/ladle.json  ← 完整模型配置 (attributes, variables, rules,       │
│  /models/crane.json     states, transitions, services, alarms, schedules)│
└─────────────────────────────────────────────────────────────────────────┘
                               │
                               │ file_path
                               ▼
┌─────────┐               ┌─────────────┐               ┌─────────────────┐
│ models  │──────────────►│  instances  │◄──────────────│instance_variables│
│(元数据)  │    1:N        │  (实例主表)  │    1:N        │   (变量值)       │
└─────────┘               └──────┬──────┘               └─────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
            ▼                    ▼                    ▼
     ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
     │instance_alar│      │instance_even│      │instance_logs│
     │    ms       │      │    ts       │      │   (可选)     │
     │  (告警表)    │      │  (事件表)    │      │  (日志表)    │
     └─────────────┘      └─────────────┘      └─────────────┘
```

---

## 常用查询示例

### 获取实例完整信息
```sql
SELECT 
  i.*,
  JSON_OBJECTAGG(iv.name, iv.value) as variables
FROM instances i
LEFT JOIN instance_variables iv ON i.id = iv.instance_id
WHERE i.id = 'ladle_001' AND i.is_deleted = FALSE
GROUP BY i.id;
```

### 查询钢水量超过 100 吨的实例
```sql
SELECT DISTINCT i.*
FROM instances i
JOIN instance_variables iv ON i.id = iv.instance_id
WHERE iv.name = 'steelAmount' AND CAST(iv.value AS DECIMAL) > 100;
```

### 查询实例的活跃告警（未清除），按等级降序
```sql
SELECT * FROM instance_alarms 
WHERE instance_id = 'ladle_001' AND status != 'cleared'
ORDER BY level DESC, triggered_at DESC;
```

### 查询待确认的严重告警（level >= 3）
```sql
SELECT * FROM instance_alarms 
WHERE status = 'triggered' AND level >= 3;
```

### 查询实例最近 24 小时的事件时间线
```sql
SELECT * FROM instance_events 
WHERE instance_id = 'ladle_001' 
  AND timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY timestamp DESC;
```

### 查询实例的最新状态变更事件
```sql
SELECT * FROM instance_events 
WHERE instance_id = 'ladle_001' AND event_type = 'state-change'
ORDER BY timestamp DESC
LIMIT 1;
```

---

## 数据清理策略

| 表名 | 保留策略 | 说明 |
|------|----------|------|
| models | 永久保留 | 模型元数据，占用极小 |
| instances | 软删除，保留 1 年 | 标记 is_deleted，定期物理删除 |
| instance_variables | 随实例删除 | 实例删除时级联删除 |
| instance_alarms | 保留 90 天 | 已清除的告警可归档到冷存储 |
| instance_events | 保留 30 天 | 定期归档到冷存储（如 S3） |
| instance_logs | 保留 7 天 | 或直送 ELK，不存本地 |

---

## model.json 文件结构参考

```json
{
  "$schema": "https://agent-studio.io/schema/v1",
  "metadata": {
    "version": "1.0",
    "name": "ladle",
    "title": "钢包智能体",
    "tags": ["logistics", "steelmaking"],
    "group": "logistics",
    "creator": "张三",
    "createdAt": "2024-06-01T10:00:00Z",
    "updatedAt": "2024-06-01T10:00:00Z",
    "description": "钢包智能体，负责盛放和运输钢水"
  },
  "attributes": {
    "capacity": { "type": "number", "default": 200, "x-unit": "ton" },
    "maxTemperature": { "type": "number", "default": 1800, "x-unit": "℃" }
  },
  "variables": {
    "steelAmount": { "type": "number", "default": 0, "x-unit": "ton" },
    "temperature": { "type": "number", "default": 25, "x-unit": "℃" }
  },
  "derivedProperties": {
    "fillRate": { "type": "number", "x-formula": "steelAmount / capacity * 100" }
  },
  "rules": {
    "capacityLimit": { "condition": "steelAmount <= capacity", ... }
  },
  "states": { ... },
  "transitions": { ... },
  "services": { ... },
  "alarms": { ... },
  "schedules": { ... }
}
```

---

## 实例数据结构参考

```json
{
  "$schema": "https://agent-studio.io/schema/v1/instance",
  "id": "ladle_001",
  "modelId": "ladle",
  "state": "empty",
  "metadata": {
    "name": "ladle_001",
    "title": "1号钢包",
    "description": "转炉跨1号钢包",
    "creator": "张三",
    "createdAt": "2024-06-01T10:00:00Z",
    "updatedAt": "2024-06-01T10:00:00Z"
  },
  "attributes": {
    "capacity": 200,
    "maxTemperature": 1800
  },
  "variables": {
    "steelAmount": 0,
    "temperature": 25,
    "carbonContent": 0,
    "steelGrade": "",
    "currentLocation": "standby_area"
  },
  "extensions": {
    "maintenance": { "usageCount": 0, "lastMaintenanceTime": null },
    "lifecycle": { "totalPours": 0, "totalSteelHandled": 0 }
  }
}
```

---

**文档版本**: 1.0  
**创建日期**: 2026-04-09
