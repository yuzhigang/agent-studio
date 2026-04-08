# Agent Studio 智能体配置规范

## 概述

本文档定义智能体（Agent）的 JSON 配置结构，用于描述工业设备、物流对象或业务实体的数字孪生。

## 文件结构

```
agent-studio/
├── agent.json          # 智能体定义（类型定义）
├── data-sources.json   # 数据源配置（集中管理）
├── ladle_001.json      # 智能体实例（具体设备）
└── AGENT.md            # 本规范文档
```

## 核心概念

### 1. 智能体定义 (agent.json)

#### 设计目标

`agent.json` 是智能体的**蓝图**，解决以下问题：

1. **统一规范** - 确保同一类设备（如所有钢包）遵循相同的结构和行为
2. **业务规则集中** - 校验逻辑、安全限制在一处定义，所有实例共享
3. **状态机复用** - 定义一次状态流转，所有实例遵循相同生命周期
4. **低代码配置** - 实例只需填写具体值，无需重复定义约束

#### 模块设计思想

| 模块 | 设计意图 | 示例 |
|-----|---------|------|
| **attributes** | 区分设备固有参数（出厂即确定）与动态状态 | 钢包容量是固定的，不会随时间变化 |
| **variables** | 定义运行时状态的数据类型和约束 | 钢水量、温度是实时变化的 |
| **rules** | 集中业务校验，保证数据一致性 | 钢水量 ≤ 容量、温度在安全范围 |
| **derivedProperties** | 避免冗余存储，自动计算派生值 | 填充率 = 钢水量 / 容量 |
| **states/transitions** | 显式建模设备生命周期 | 空包→接钢→满包→倾倒→空包 |
| **services** | 封装对设备的操作，有副作用 | 装载、倾倒、移动等动作 |
| **functions** | 复用计算逻辑 ，无副作用| 温降计算、负载计算等 |

#### 结构示例

```json
{
    "metadata": { "name": "ladle", "title": "钢包智能体" },
    "attributes": {
        "capacity": { "type": "number", "minimum": 0, "maximum": 500 }
    },
    "variables": {
        "steelAmount": { "type": "number", "rules": { "pre": [...] } }
    },
    "derivedProperties": {
        "fillRate": { "formula": "this.variables.steelAmount / this.attributes.capacity * 100" }
    },
    "rules": {
        "capacityLimit": { "condition": "...", "onViolation": {...} }
    },
    "states": { "empty": {...}, "full": {...} },
    "transitions": { "emptyToFull": {...} },
    "services": { "loadSteel": {...}, "pour": {...} }
}
```

### 2. 数据源配置 (data-sources.json)

集中管理所有外部数据源连接，实例通过 `source` 字段引用。

```json
{
    "$schema": "https://agent-studio.io/schema/data-sources/v1",
    "sources": {
        "plc_line_a": {
            "type": "opcua",
            "endpoint": "opc.tcp://192.168.1.100:4840",
            "namespace": "urn:siemens:plc:line_a",
            "auth": { "type": "certificate", ... }
        },
        "factory_mqtt": {
            "type": "mqtt",
            "broker": "mqtt://iot.steelplant.com:1883",
            "auth": { "type": "username", ... }
        },
        "mes_system": {
            "type": "http",
            "baseUrl": "https://mes.steelplant.com/api/v1",
            "auth": { "type": "bearer", ... }
        }
    }
}
```

### 3. 智能体实例 (ladle_001.json)

具体设备的运行时配置，包含数据源绑定。

## 类型定义与实例的关系

### 核心设计思想

Agent Studio 采用**类型-实例分离**的设计模式，类比面向对象编程中的**类与对象**关系：

| 概念 | 对应文件 | 角色 | 示例 |
|-----|---------|------|------|
| **类型定义** | `agent.json` | 描述一类智能体的结构、行为和规则 | "钢包"这类设备的通用定义 |
| **实例** | `ladle_001.json` | 具体设备的运行时状态和数据绑定 | "1号钢包"这个具体设备 |

### 类型定义 (agent.json) 的职责

`agent.json` 是**元数据模板**，定义了：

1. **结构规范** - 变量有哪些字段、数据类型、取值范围
2. **业务规则** - 校验逻辑（如容量上限、温度安全范围）
3. **状态机** - 状态定义和转换规则（空包→接钢→满包→倾倒）
4. **派生计算** - 填充率、剩余寿命等计算逻辑
5. **服务接口** - 装载、倾倒、移动等操作定义

```json
// agent.json - 类型定义（定义"钢包"长什么样）
{
    "metadata": { "name": "ladle", "title": "钢包智能体" },
    "attributes": {
        "capacity": {
            "type": "number",
            "minimum": 0,
            "maximum": 500,
            "default": 200
        }
    },
    "variables": {
        "steelAmount": {
            "type": "number",
            "minimum": 0,
            "maximum": 500,
            "rules": { "pre": [{"rule": "capacityLimit"}] }
        }
    },
    "rules": {
        "capacityLimit": {
            "condition": "this.variables.steelAmount <= this.attributes.capacity",
            "onViolation": { "action": "reject", ... }
        }
    },
    "states": {
        "empty": { "name": "empty", "title": "空包", "initialState": true },
        "full": { "name": "full", "title": "满包" }
    },
    "transitions": {
        "emptyToFull": { "from": "empty", "to": "full", ... }
    }
}
```

### 实例 (ladle_001.json) 的职责

实例文件是**运行时实体**，包含：

1. **具体标识** - `id`: "ladle_001"
2. **属性值** - 该设备的固定参数（容量200吨）
3. **变量状态** - 当前钢水量、温度、位置等实时值
4. **数据源绑定** - 与PLC、MQTT、MES的实际连接配置

```json
// ladle_001.json - 实例（定义"这个钢包"的当前状态）
{
    "id": "ladle_001",
    "metadata": { "name": "ladle", "title": "1号钢包" },
    "attributes": {
        "capacity": 200        // 具体值，必须符合 agent.json 中的定义
    },
    "variables": {
        "steelAmount": {
            "value": 150,       // 当前状态值
            "bind": { ... }     // 数据源绑定（实例特有）
        }
    },
    "state": {
        "current": "full"     // 当前状态机状态
    }
}
```

### 类型与实例的对应关系

```
┌─────────────────────────────────────────────────────────────┐
│                      agent.json (类型定义)                    │
├─────────────────────────────────────────────────────────────┤
│  metadata.name: "ladle"                                     │
│  attributes.capacity: {type: number, min: 0, max: 500}     │
│  variables.steelAmount: {type: number, rules: [...]}       │
│  rules.capacityLimit: {...}                                │
│  states: {empty, receiving, full, pouring, maintenance}    │
└────────────────────┬────────────────────────────────────────┘
                     │ 引用/验证
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    ladle_001.json (实例)                      │
├─────────────────────────────────────────────────────────────┤
│  id: "ladle_001"                                            │
│  metadata.name: "ladle"  ← 必须与类型定义匹配                  │
│  attributes.capacity: 200  ← 必须在 [0,500] 范围内            │
│  variables.steelAmount.value: 150  ← 必须符合类型定义          │
│  variables.steelAmount.bind: {...}  ← 实例特有配置             │
│  state.current: "full"  ← 必须是 states 中定义的有效状态       │
└─────────────────────────────────────────────────────────────┘
```

### 实例对类型的验证

实例创建和更新时，运行时需要验证：

| 验证项 | 规则 | 示例 |
|-------|------|------|
| `metadata.name` 匹配 | 实例的 name 必须等于类型定义的 name | `ladle` ↔ `ladle` ✓ |
| 属性值范围 | 必须在类型定义的 min/max 范围内 | `capacity: 200` 在 [0,500] ✓ |
| 变量类型 | 必须符合类型定义的数据类型 | `steelAmount` 是 number ✓ |
| 状态有效性 | 必须是 states 中定义的合法状态 | `full` 在状态列表中 ✓ |
| 规则触发 | 修改时触发类型定义中的校验规则 | `steelAmount <= capacity` ✓ |

### 一对多关系

一个类型定义可以对应多个实例：

```
agent.json (钢包类型定义)
    ├── ladle_001.json (1号钢包：容量200吨，连铸线A)
    ├── ladle_002.json (2号钢包：容量300吨，连铸线B)
    ├── ladle_003.json (3号钢包：容量200吨，备用)
    └── ...
```

每个实例共享相同的业务逻辑（规则、状态机），但拥有独立的状态和绑定配置。

## 实例配置结构

```json
{
    "$schema": "https://agent-studio.io/schema/v1",
    "id": "ladle_001",
    "metadata": {
        "name": "ladle",
        "title": "1号钢包"
    },
    "attributes": {
        "capacity": 200,
        "maxTemperature": 1800
    },
    "variables": {
        "steelAmount": {
            "value": 150,
            "bind": { ... }
        }
    },
    "state": {
        "current": "full"
    }
}
```

## 数据源绑定规范

### 绑定对象结构

每个变量可选 `bind` 字段，定义数据源映射：

```json
"variableName": {
    "value": 150,                    // 默认值（绑定失败时使用）
    "bind": {
        "source": "plc_line_a",      // 引用 data-sources.json 中的 key
        "path": "ns=2;s=Ladle01.Weight",   // OPC UA 节点路径
        "topic": "position/ladle/001",     // MQTT Topic（与 path 二选一）
        "selector": "$.value",       // JSONPath 选择器（复杂结构时使用）
        "transform": "value * 0.001" // 数值转换表达式
    }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `source` | string | 是 | 数据源标识，对应 data-sources.json 中的 key |
| `path` | string | 条件 | OPC UA 节点路径或 HTTP API 端点 |
| `topic` | string | 条件 | MQTT Topic，用于 MQTT 类型数据源 |
| `selector` | string | 否 | JSONPath 表达式，从复杂数据结构中提取目标字段 |
| `transform` | string | 否 | JavaScript 表达式，对提取的值进行转换 |

### 数据源类型与绑定方式

| 数据源类型 | 绑定字段 | 示例 |
|-----------|---------|------|
| OPC UA | `source` + `path` | `"path": "ns=2;s=Ladle01.Weight"` |
| MQTT | `source` + `topic` | `"topic": "status/ladle/001"` |
| HTTP | `source` + `path` | `"path": "/ladles/001/status"` |
| PostgreSQL | `source` + `table` + `column` | `"table": "shift_records"` |

### selector 使用场景

当数据源返回复杂 JSON 结构时，使用 `selector` 提取目标字段：

**原始数据：**
```json
{
    "timestamp": "2025-04-09T10:30:00Z",
    "position": {
        "zone": "converter_1",
        "x": 1250.5,
        "y": 3680.0
    }
}
```

**绑定配置：**
```json
"currentLocation": {
    "value": "converter_1",
    "bind": {
        "source": "factory_mqtt",
        "topic": "position/ladle/001",
        "selector": "$.position.zone",
        "transform": "value.toLowerCase()"
    }
}
```

### transform 表达式

`transform` 中可使用 `value` 变量代表 selector 提取的结果：

| 场景 | transform 示例 |
|-----|---------------|
| 单位转换 | `"value * 0.001"` (kg → 吨) |
| 数值取整 | `"Math.round(value)"` |
| 精度控制 | `"parseFloat(value.toFixed(3))"` |
| 字符串格式化 | `"value.toUpperCase()"` / `"value.toLowerCase()"` |
| 坐标缩放 | `"value / 1000"` (mm → m) |
| 日期格式化 | `"new Date(value).toISOString()"` |
| 数值限幅 | `"Math.max(-90, Math.min(90, value))"` |
| 布尔转换 | `"value === 1 \|\| value === true"` |
| 字符串替换 | `"value.replace(/\\s/g, '_')"` |
| 类型转换 | `"parseInt(value)"` / `"parseFloat(value)"` |
| 透传 | `"value"` |

### selector 语法 (JSONPath)

| 语法 | 含义 | 示例 |
|-----|------|------|
| `$` | 根对象 | `"$"` |
| `$.field` | 对象属性 | `"$.position.zone"` |
| `$[index]` | 数组索引 | `"$.sensors[0]"` |
| `$[*]` | 所有数组元素 | `"$.readings[*].value"` |
| `$[?expr]` | 条件过滤 | `"$.sensors[?type=='temp'].value"` |

### PostgreSQL 数据库绑定

对于关系型数据库，使用 SQL 查询方式绑定：

```json
"shiftId": {
    "value": "A-20250409-1",
    "bind": {
        "source": "production_db",
        "table": "shift_records",
        "column": "shift_id",
        "join": "users ON shift_records.operator_id = users.id",
        "where": "ladle_id = '001' AND status = 'active'",
        "orderBy": "created_at DESC",
        "limit": 1,
        "selector": "$.shift_id",
        "polling": 60000
    }
}
```

#### PostgreSQL 绑定字段

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `source` | string | 是 | 数据源标识，对应 data-sources.json 中的 PostgreSQL 配置 |
| `sql` | string | 是 | 完整 SQL 查询语句，应返回单行数据 |
| `selector` | string | 是 | JSONPath 选择器，从查询结果中提取目标字段，如 `"$.fieldname"` |
| `transform` | string | 否 | 数值转换表达式 |
| `polling` | number | 否 | 轮询间隔(ms)，数据库默认按需查询或定时轮询 |

#### SQL 查询示例

```json
"shiftId": {
    "value": "A-20250409-1",
    "bind": {
        "source": "production_db",
        "sql": "SELECT shift_id FROM shift_records WHERE ladle_id = '001' AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        "selector": "$.shift_id",
        "polling": 60000
    }
}
```

**JOIN 查询：**
```json
"operatorName": {
    "bind": {
        "source": "production_db",
        "sql": "SELECT u.name as operator_name FROM shift_records sr JOIN users u ON sr.operator_id = u.id WHERE sr.ladle_id = '001' ORDER BY sr.created_at DESC LIMIT 1",
        "selector": "$.operator_name",
        "polling": 60000
    }
}
```

**带子查询：**
```json
"qualityCheckStatus": {
    "bind": {
        "source": "production_db",
        "sql": "SELECT status FROM quality_checks WHERE ladle_id = '001' AND heat_id = (SELECT heat_id FROM heat_records WHERE ladle_id = '001' ORDER BY created_at DESC LIMIT 1) ORDER BY created_at DESC LIMIT 1",
        "selector": "$.status"
    }
}
```

## 实例扩展字段能力

实例可以定义**类型定义中未包含**的扩展字段，实现业务的灵活定制。

### 设计原则

- **类型定义 (agent.json)**：规定所有实例必须遵循的基础结构和行为
- **实例 (ladle_001.json)**：在类型定义基础上，可添加实例特有的扩展字段

### 扩展示例

**agent.json 中定义的变量（通用）：**
```json
"variables": {
    "steelAmount": { "type": "number" },
    "temperature": { "type": "number" },
    "status": { "type": "string" }
}
```

**ladle_001.json 中的扩展字段（实例特有）：**
```json
"variables": {
    "steelAmount": { "value": 150, ... },
    "temperature": { "value": 1650, ... },
    "status": { "value": "full", ... },
    "shiftId": {                              // 扩展字段：班次信息
        "value": "A-20250409-1",
        "bind": { "source": "production_db", ... }
    },
    "operatorName": {                         // 扩展字段：操作员
        "value": "张三",
        "bind": { "source": "production_db", ... }
    },
    "plannedCastingTime": {                   // 扩展字段：计划时间
        "value": "2025-04-09T14:00:00Z",
        "bind": { "source": "production_db", ... }
    }
}
```

### 扩展字段的使用场景

| 场景 | 说明 |
|-----|------|
| **产线特有数据** | 不同产线的钢包可能关联不同的业务系统 |
| **临时监控指标** | 试验阶段的指标，成熟后再纳入类型定义 |
| **第三方系统对接** | 特定系统（如物流跟踪、质检系统）的对接字段 |
| **个性化配置** | 不同车间、班组的定制化需求 |

### 运行时行为

- **验证时**：扩展字段不受类型定义的约束规则限制（除非显式配置）
- **派生计算**：扩展字段可被 derivedProperties 公式引用（如果运行时支持）
- **序列化**：扩展字段随实例完整序列化保存

## 设计原则

1. **分离关注点**：数据源连接配置与实例配置分离，实例只保留轻量级引用
2. **默认值兜底**：每个变量必须有 `value` 字段，作为绑定失败时的默认值
3. **可选绑定**：非所有变量都需要绑定，静态配置可省略 `bind` 对象
4. **表达式安全**：`transform` 表达式应在沙箱环境中执行，避免安全风险
5. **层级清晰**：`attributes`（固定）与 `variables`（动态）严格区分

## 完整示例

参见：
- [agent.json](agent.json) - 钢包类型定义（通用结构、规则、状态机）
- [data-sources.json](data-sources.json) - 数据源配置（连接管理）
- [ladle_001.json](ladle_001.json) - 钢包实例（具体设备的状态和绑定）

## 版本历史

| 版本 | 日期 | 变更 |
|-----|------|------|
| 1.0 | 2025-04-09 | 初始版本，定义基础结构和绑定规范 |
| 1.1 | 2025-04-09 | 增加 PostgreSQL 数据源绑定支持；增加实例扩展字段能力说明 |
