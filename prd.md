

[toc]



# 概述

物模型（ThingModel）是本工业数据平台对物理设备（如传感器、执行器、PLC、机床等）进行数字化描述的核心。它通过抽象和标准化设备的能力，提供了一种通用的方式来理解、交互和管理不同类型和协议的工业设备。物模型定义了设备的**静态属性**、**动态属性**、**状态**、**事件**、**告警**以及可执行的**服务**，使得上层应用能够以统一的接口与设备进行通信，而无需关心底层复杂的协议细节。

平台中的所有物模型及过程配置均通过 **DF Admin** 云端管理系统进行统一设计，物模型产生的状态、事件和过程可以通过http api获取，并可以通过消息中心转发到其他业务系统。

#  物模型定义(ThingModel)

物模型是对一类设备能力的标准化模板，它不包含设备实例的运行时数据，而是描述了该类设备“是什么”以及“能做什么”。

```JSON
{
  "id": "tm_induction_furnace_v1",
  "code": "induction_furnace",
  "name": "感应炉",
  "version": "1.0.0",
  "remark": "用于金属熔炼的感应炉设备物模型。",
  "staticAttributes": [],
  "properties": [],
  "statuses": [],
  "events": [],
  "services": [],
  "processes":[], 
  "children": [ // 子物模型，比如：对于炼钢过程，可以创建一个炼钢物模型
    {
      "code": "bof", // 子模型的实例编码，在父模型内唯一
      "name": "转炉",
      "modelId": "bof_v2", // 引用的物模型ID
      "remark": "转炉"
    },
    {
      "code": "lf",
      "name": "LF",
      "modelId": "lf_v1"
    }
  ]
}
```

## 静态属性 (Static Attributes)

定义设备的固有参数，这些参数在设备生命周期内通常不变或仅通过配置修改，不直接绑定实时数据流。

```json
{
  "code": "rated_power",
  "name": "额定功率",
  "valueType": "float",
  "unit": "kW",
  "remark": "设备设计额定功率。",
  "icon":"",
  "category": "铭牌参数", 
  "rank":1, 
  "accessMode": "Read",
  "constraints": {
    "required": true,
    "defaultValue": 5000.0
  }
}
```

##   动态属性 (Properties)

定义设备运行过程中实时变化的数据点，直接关联到边缘网关采集的数据源。

```JSON
{
  "code": "current_temperature",
  "name": "炉内温度",
  "valueType": "float",
  "unit": "℃",
  "accessMode": "Read",
  "icon":"",
  "category": "测量", 
  "rank":1, 
  "remark": "炉内温度",
  "constraints": {
      "defaultValue":1000,
      "min": 0.0,
      "max": 2000.0,
      "deadband": {
          "type": "Percentage", // 百分比死区
          "value": 0.01        // 功率变化超过1%才上报
      }
  }
}
```
> 以下两个字段不应该在定义时配置，而是在每个物模型实例上配置：
>
>  "bindingSource":"tdengine", // 默认是时序数据库的标签，但也可能是其他来源，如数据库的某个表； "bindingTag": "$tag_furnace_temp", // 关联的数据采集平台的点位， 如数据库表的某列
>
> 当实例有主键属性时，可以在数据表的某行记录的某列获取到对应的属性配置。当`primaryKey`为`true`时，该属性值（如‘炉号’）可被用于反向查询或唯一标识一个物模型实例，即使不知道其系统ID。

##  状态 (Statuses)

<img src="http://files.youpinhe.com/typora/image-20250829162331097.png" alt="image-20250829162331097" style="zoom:50%;" />

定义设备所有可能存在的、互斥的业务状态。它们是状态机中的“节点”。

```json
[
 	// group:"run_state" 定义了运行相关的状态
    { "group":"run_state", "code": "off",  "name": "关机" },
    { "group":"run_state", "code": "working", "name": "工作中" },
    
    // group:"maintenance_state" 定义了维护相关的状态，与运行状态正交
    { "group":"maintenance_state", "code": "normal", "name": "正常" },
    { "group":"maintenance_state", "code": "scheduled_maintenance", "name": "计划内维护" }
]
```
> 层次状态： `working` 状态包括：`working.melting`, `working.heating`等
> 状态：物模型同时存在多个独立的状态表征，即正交状态， 此处通过`group`字段字段分组，实现同时有多个不同类型的状态。

##   事件 (Events)

事件（Events）定义了设备在特定条件下发生的、重要的状态迁移或业务信号。在状态机模型中，每个事件都描述了一个从起始状态（`from`）到目标状态（`to`）的有效路径及其触发条件。

> 事件也可以理解为变迁（Transition），表示从一个状态迁移到另一个状态时，触发的对应的事件。

<img src="http://files.youpinhe.com/typora/image-20250829162418225.png" alt="image-20250829162418225" style="zoom:50%;" />

- **定义**:
  - `code`: 事件的唯一编码。
  - `name`: 事件的名称。
  - `from`: 允许触发此事件的一个或多个起始状态码。可以使用 `"*"` 代表任意状态或与状态无关。
  - `to`: 事件触发成功后的目标状态码。
  - `trigger`: 触发此事件必须满足的条件，详见“触发器详细定义”。
  - `outputs`: 事件触发时附带的输出数据。

```JSON
{
    "code": "start_working",
    "name": "开始工作",
    "level": "warning", // 事件等级，如 `info`, `warning`, `critical`
    "category": "working", // 分类
    "type": "event", // 种类，如：event、alarm等 
    "multiple": false,  // 是否允许该物模型下多次触发该事件，默认只能一次
    "from": ["standby"], // 条件：当前处于standby状态（可以使用 "*" 代表不限状态或与状态无关）
    "trigger": { // 事件触发的原因，基于当前standby状态或空
      "code": "trigger1", // 触发器编码，以方便索引 
      "type": "condition",
       // "type":"event", 事件类型
      // "eventCode":"heating",
      "expression": "$.properties.power_consumption > 500",
      "duration": 5
    },
    actions:[{
        "label": "更改状态",
        "expression":"$.setStatus(\"working\")"
    }],
    "to": "working",   //结果：导致处于working状态（可以使用 "*"代表状态没有变化或与状态无关）
    "outputs": [{ 
        "name": "furnace_no", "valueType": "string", "remark":"炉号", "expression": "$.properties.fn" 
    }]
}
```
> 解释：当前处于standby状态，同时满足了trigger的表达式条件，导致 start_working 事件的发生，并使实例处于working的状态。
>
> **事件是状态发生变化的原因**（但不一定触发状态变更，而是其他属性发生变更，此处的状态理解为狭义的物模型状态）。当物模型处于某个状态时，满足触发条件时发生一次状态迁移，同时改变状态（但也可能不发生状态变更）。
>
> 基于条件的触发器，事件发生后一定要改变状态，否则条件将会持续满足。 所以状态应该作为条件的一部分。

> 关于延迟事件：由于事件的发生并不总是导致状态变更，但是有时又需要依赖于某件事件发生后，延时特定时间后触发一个新事件。此处可以利用层次状态，即某件事件发生后强制将物模型的状态改为子状态（如`standby.xxx`），这样就可以实现**某个事件发生后的特定时间内**触发一个新事件。



##  服务 (Services)

定义设备可被远程调用的操作，设备可运行的上下文均为实例范围内，如：更改属性或状态等。

  ```json
  {
    "code": "adjust_furnace_power",
    "name": "调节炉子功率",
    "inputs": [{ "name": "targetPower", "valueType": "float", "remark":"功率" }],
    "outputs": [{ "name": "success", "valueType": "boolean", "remark":"是否成功" }],
    "scriptEngine": "javascript",
    "script": "$.set('power_kw_setting', targetPower); return {success: true};"
  }
  ```

## 过程 (Process)

过程定义了由一系列物模型事件驱动的、具有开始和结束标记的生产或操作周期。

###   过程结构定义

```JSON
{
  "code": "melting_cycle",
  "name": "冶炼周期",
  "remark": "冶炼周期",
  "thingModel": "steel_making", // 所属物模型，即：该过程关联到哪个物模型
  "keyExpression": "$.children.bof.events.start_working.heat_no", // 这里依赖开始或结束事件上报的payload里的值
  "multiple": false,    // 是否允许有多个相同流程，在同一个主键下（例如，同一炉次允许多次冶炼）
  "startTrigger":  [{
        "id": "auto_start", // 给每个触发器一个唯一ID
        "thingModel": "bof",
        "eventCode": "start_working",
        "occurredCount": 1 // 默认为第一次，-1表示最后一次
   }],
   "endTrigger":  [{
            "id": "normal_end",
            "thingModel": "induction_furnace",
            "eventCode": "tapping_end",
         	"occurredCount": 1, // 默认为第一次，-1表示最后一次
        },{
            "id": "abort_end",
            "thingModel": "induction_furnace",
            "eventCode": "emergency_stop",
            "occurredCount": 1 // 默认为第一次，-1表示最后一次
     }],
  	"defaultDuration": 3600,
  	"maxDuration": 7200,
 	"minDuration": 600,
  	"rank": 1,  // 顺序值，用于流程排序或特定展示
 	"remark": "", // 备注
 	"parentCode": "" ,// 父流程code，支持嵌套流程,
    "outputs": [{ 
        "name": "furnace_no", "valueType": "string", "remark":"炉号", "expression": "$.children.bof.properties.furnace_no" 
    }]
}
```

> 通过为物模型增加子模型（children字段）表达更高层面的物模型，实现跨物模型的过程定义。
>
> startTrigger 和 endTrigger 设计为数组的原因是：可能开始或结束是可以由多个事件触发的。多个事件是OR的关系，AND 关系会存在等待多个条件都满足（时间不一致）的问题，比较复杂。OR的逻辑关系能满足大部分情形。

> `startTrigger`中的`start_working`事件被触发时，其`outputs`中会包含一个`heat_no`（炉号）的字段。`keyExpression`配置为`$.children.bof.events.start_working.heat_no`，意味着系统会提取这个炉号作为该过程实例的唯一业务键（`processKey`），后续的结束事件也需要通过此键来匹配。

###  核心处理逻辑与运行机制

边缘网关中的Process Manager负责监听`startTrigger`和`endTrigger`中定义的事件，创建、更新和完成过程实例。对于超时、乱序或孤立的事件，系统会根据预设规则进行处理或告警。

**开始事件处理**：

1. 当 `eventCode` 定义的事件触发时，`Process Manager` 检查当前 `key_value` 下是否有活跃的对应过程实例。
2. 如果找到一个未打开始戳的实例，或者 `multiple` 允许且 `occurredCount` 匹配，则更新该实例的 `start_time`。
3. 如果没有找到活跃实例且允许新开，则创建一个新的过程实例记录，并设置 `start_time`。
4. `occurredCount`：如果配置为1，则只记录第一次开始事件；如果为-1，则更新为发生在当前 `key_value` 和设备物模型组合下的最新开始事件。

**结束事件处理**：

1. 当 `eventCode` 定义的事件触发时，`Process Manager` 尝试找到一个匹配的*活跃*过程实例（以 `start_time` 已设置但 `end_time` 为空为特征）。

2. 如果找到，则更新该实例的 `end_time`，并计算 `duration` (`end_time - start_time`)。

3. `occurredCount` 逻辑同 `occurredCount`。

4. 如果找不到对应的活跃开始事件，则可能该结束事件为孤立事件，可根据配置舍弃或触发告警。

**持续时间计算与修正**：

1. 一旦 `start_time` 和 `end_time` 都可用，计算原始 `duration`。
2. **数据质量过滤**：`minDuration` 和 `maxDuration` 用于过滤异常值。如果计算出的 `duration` 小于 `minDuration` 或大于 `maxDuration`，则该过程实例可能被标记为异常，或其持续时间被修正为默认值、最小/最大值。`defaultDuration`在以下情况下使用：
   *   只有开始事件，但长时间没有结束事件：`end_time = start_time + defaultDuration` (标记为估算完成)。
   *   只有结束事件，但没有开始事件： `start_time = end_time - defaultDuration` (标记为估算完成)。
3. **过程状态持久化**：计算完成的流程实例（或阶段性更新的活跃实例）将状态持久化到 `process_instances` 表中，以供后续查询、分析和报表生成。

###  嵌套过程

`parentCode` 字段允许定义复杂的多级生产过程。`Process Manager` 需要额外逻辑来管理父子流程的生命周期：

*   子流程的开始/结束可能影响父流程的状态或属性（例如，所有子流程完成后父流程才变为完成）。
*   父流程的 `keyExpression` 可以包含子流程的 `keyExpression` 中的部分信息，以确保关联性。

###  状态持久化与故障恢复

为确保系统可靠性，边缘网关必须具备状态持久化能力。所有活跃（ACTIVE）的过程实例以及物模型实例的最新状态（status）必须被持久化到本地的非易失性存储中。网关重启后，会从本地存储加载这些信息，以恢复中断的流程并继续执行。

###  流程的使用方法

确定某个流程后，就能确定这个流程下各的属性的取值时间间隔，将时序数据进行分片。例如：当知道感应炉冶炼的开始时间和结束时间，就可以知道某个物料被设备处理加工时的过程参数，即： 直接获取某个属性的开始和结束时间段。



# 物模型上下文(Context)

##   触发器 (Trigger) 详细定义

触发器（Trigger）详细描述了一个事件被触发的具体方式。

###   触发器结构

```JSON
"trigger": {
  "type": "condition", // 触发器类型: condition, timeout, schedule
  // ... 其他参数
}
```

### `condition` 类型

由数据满足特定表达式来触发。

- `expression`: 谓词表达式。
- `duration`: 一个整数，定义了表达式需要持续为真的时间，单位为秒。
- `count`: 一个整数，定义了表达式需要连续为真的采集次数。

```JSON
"trigger": {
  "type": "condition",
  "expression": "$.properties.current_temperature > 1600",
  "duration": 10,// 与count 二选一，可空
  "count": 3, // 与duration 二选一，可空
}
```

### `timeout` 类型

当设备在起始状态（`from`）持续停留超过指定时间后自动触发。如果起始状态设为`*`，则表示任何状态停留超过指定时间后触发。

- `duration`: 一个整数，定义了超时时间，单位为秒。

```json
  // 在“预热”状态停留超过 1200 秒（20分钟）
  "trigger": {
    "type": "timeout",
    "duration": 1200
  }
```

### `schedule` 类型

按照预设的CRON表达式或固定速率触发。

- `cron`: CRON表达式字符串。

```json
  // 每小时的第0分钟触发
  "trigger": {
    "type": "schedule",
    "cron": "0 0 * * * ?"
  }
```

## 表达式语言 (Expression Language)

**上下文 (`$`)**代表当前的物模型实例。

- `$.properties.{code}`: 获取动态属性的当前值。
- `$.staticAttributes.{code}`: 获取静态属性的值。
- `$.status`: 获取当前的状态码。
- `$.children.bof.properties.{code}`: 获取子模型`bof`的属性的当前值。

**历史值访问**: 系统支持访问状态或动态属性的上一个值，通过在变量后附加 `__LAST` 实现。这对于检测状态变化或值的“边沿”（例如，从真变为假）非常有用。

- **示例 (状态)**: `$.status == 'working' && $.status__LAST == 'standby'`
- **示例 (属性)**: `$.properties.switch_on == false && $.properties.switch_on__LAST == true`

##  服务脚本执行环境

- **安全**: 脚本在沙箱中执行，无法访问文件系统、网络或执行系统命令。
- **资源限制**: 脚本执行有严格的超时和内存限制。
- **预定义API**:
  - `$.get('{propertyCode}')`: 获取属性值。
  - `$.getLast('{propertyCode}')`: 获取属性的上一次取值。
  - `$.set('{propertyCode}', value)`: 设置可写属性值。



# 物模型实例

## 物模型实例(ThingModel Instance)

以下描述一个具体的物联网实例：

```json
{
    "id":"",
    "code":"",
    "name":"",
    "parentId": "steel_making_instance_1", // 父物模型实例
    "thingModel":"induction_furnace",
    "properties":[{
      "code": "current_temperature",
      "name": "炉内温度",
      "valueType": "float",
      "unit": "℃",
      "reamrk":"",
      "isCustom": true, // 是否是自定义的属性
      "constraints": { // 覆盖物模型的配置
            "max": 1800.0 // 例如，这个实例的最高温度限制不同
      },
      "binding":{
          "source": "mqtt",
          "tag": "/devices/furnace_A_101/vibration/z"
      }
    }],
    "staticAttributes":[{
        "code": "capacity",
        "name": "能力",
        "value": 1300,
        "isCustom": true, // 是否是自定义的属性
    }]
}
```
> 注意： 物模型实例是根据物模型模板创建出来的，它们的父子关系在配置时已经明确。

## 事件实例（Event Instance)

物模型的事件记录：

```json
{
    "id":"",
    "version": "1.0.0",
    "deviceCode":"", // 设备编码
    "eventCode":"", // 事件编码
    "eventTime":"", // 事件发生时间
    "eventName": "开始工作",  // 冗余      
    "eventLevel": "info",     // 冗余事件等级
    "eventType": "event", // 冗余事件类型
    "fromStatus":"", // 上一个状态
    "toStatus":"", // 当前状态
    "trigger": { // 因何触发器触发该事件
      "code": "trigger1", // 触发器编码，以方便索引 
      "type": "condition",
      "expression": "$.properties.power_consumption > 500",
      "duration": 5
    },
    "payload":{ // event触发的output数据
        "heat_no":"",
    }, 
}
```


## 过程实例 (Process Instance)

过程定义的一次具体执行。

```JSON
{
  "id": "pi_123e4567-e89b-12d3-a456-426614174000",
  "version": "1.0.0",
  "processCode": "melting_cycle",
  "deviceCode": "furnace_01",
  "processKey": "F20250924001",
  "startStatus": "Working", // 开始事件时所处的状态
  "endStatus": "Finished", // 结束事件时所处的状态
  "quality": "good", // 是否正常开始或结束:good bad uncertain
  "thingModel": "induction_furnace", // 发生此过程的物模型编码
  "startTriggerId": "auto_start",  // 明确记录是由哪个触发器开始的
  "endTriggerId": "normal_end",     // 明确记录是如何结束的 
  "startTime": "2025-09-24T10:00:00.000Z",
  "startEventId":"", // 关联的开始事件实例的Id
  "endTime": "2025-09-24T10:45:30.000Z",
  "endEventId":"", // 关联的结束事件实例的Id
  "duration": 2730,
  "payload":{ //  process定义时触发的output数据
       "furnace_no":"",
  },
}
```

## 运行流程

### 订阅数据源

在物模型实例的配置上有以下的定义：

```json
"binding":{
    "source": "mqtt",
    "tag": "/devices/furnace_A_101/vibration/z"
}
```

程序加载时启动以下流程：

- **加载所有物模型实例配置**：从您的配置中心（如数据库或配置文件）加载所有需要运行的物模型实例。
- **遍历实例的属性**：对每个实例，遍历其`properties`列表。
- **筛选MQTT数据源**：检查每个属性的`binding.source`是否为`"mqtt"`。

- **提取并注册Topic**：如果`source`是`"mqtt"`，就提取`binding.tag`的值。这个值就是您的MQTT客户端需要订阅的主题。
- **建立映射关系**：在内部建立一个从 **MQTT主题** 到 **`(物模型实例ID, 属性Code)`** 的映射表。这至关重要，因为当您收到消息时，需要通过这个映射表快速定位到应该更新哪个实例的哪个属性。

### 触发物模型状态变更

现在，我们来描述当一条MQTT消息到达后，整个物模型逻辑是如何被一步步驱动的。

假设我们有一个“感应炉”物模型，其中定义了一个事件`start_working`，它的触发条件是功率持续5秒超过500kW，并且当前状态为“待机”。

**流程图:** `MQTT消息` -> `数据绑定` -> `属性更新` -> `触发器评估` -> `事件生成` -> `状态变更` -> `(可选)过程驱动`

**详细步骤分解：**

#### 第1步：MQTT消息接收与路由

程序通过MQTT客户端收到了一个消息。

- **Topic**: `/furnaces/furnace_A/power`
- **Payload**: `650.5`

程序立即查询在启动时建立的映射表，发现这个Topic对应的是**“感应炉实例A”**的**`power_consumption`**属性。

#### 第2步：动态属性（Property）值更新

程序将“感应炉实例A”的`power_consumption`属性的当前值更新为 `650.5`。 根据文档，系统还应记录该属性的上一个值（`__LAST`），以支持边沿检测等复杂逻辑。例如，上一个值是`480.0`。

#### 第3步：触发器（Trigger）评估 【核心驱动步骤】

**在每次动态属性更新后**，系统必须扫描该物模型实例所属的物模型定义中所有的`events`，并重新评估它们的`trigger`条件。

让我们来看`start_working`事件的定义：

```json
{
    "code": "start_working",
    "name": "开始工作",
    "from": ["standby"], // 1. 状态前置条件
    "to": "working",
    "trigger": {
      "type": "condition",
      "expression": "$.properties.power_consumption > 500", // 2. 表达式条件
      "duration": 5 // 3. 持续时间条件
    }
}
```

系统开始对“感应炉实例A”评估此触发器：

1. **检查`from`状态**：系统检查“感应炉实例A”的当前状态（`$.status`）。假设当前状态是`standby`，这满足了`"from": ["standby"]`的条件。
2. **评估`expression`**：系统使用当前实例的上下文（`$`）来解析表达式。
   - `$.properties.power_consumption`被替换为刚刚更新的值 `650.5`。
   - 表达式变为 `650.5 > 500`，结果为 **`true`**。
3. **检查`duration`**：
   - 由于表达式结果为`true`，系统启动或更新一个计时器。
   - 系统会持续监测后续收到的功率数据。如果`power_consumption`的值连续`5`秒都保持在`500`以上，那么`duration`条件才算满足。
   - 如果在此期间，功率一度低于500，计时器将重置。

#### 第4步：事件（Event）生成与状态变更

假设5秒后，功率一直大于500，`duration`条件满足。 此时，`from`状态、`expression`、`duration`三个条件**全部满足**。

1. **触发事件**：系统判定`start_working`事件被成功触发。

2. **生成事件实例**：系统会创建一个`Event Instance`记录，包含事件编码、发生时间、触发器信息、输出的`payload`等，并进行持久化或发送通知。

   ```json
   // 生成一个类似这样的事件实例
   {
     "id": "evt_...",
     "deviceCode": "furnace_A",
     "eventCode": "start_working",
     "eventTime": "...",
     "fromStatus": "standby",
     "toStatus": "working",
     // ...
   }
   ```

3. **执行状态变更**：根据事件定义中的`"to": "working"`，系统将“感应炉实例A”的当前状态更新为`working`。

#### 第5步：（可选）驱动过程（Process）逻辑

如果系统中定义了一个“冶炼周期”过程（Process），并且它的`startTrigger`配置为监听`start_working`事件。

```json
"startTrigger":  [{
    "id": "auto_start",
    "thingModel": "induction_furnace", // 或其父模型
    "eventCode": "start_working"
}]

```

那么，当`start_working`事件实例生成时：

1. **过程管理器（Process Manager）**会监听到这个事件。
2. 它会根据`process`的定义，创建一个新的**过程实例（Process Instance）**，记录其`processKey`（如炉号）、`startTime`（即事件发生时间）等信息。这个过程实例的状态变为“活跃”。
3. 这个过程会一直运行，直到监听到`endTrigger`中定义的某个结束事件（如`tapping_end`），届时它会更新过程实例的`endTime`和`duration`。









