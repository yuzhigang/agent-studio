# Agent Studio DSL 与外部算法包设计文档

## 1. 背景与目标

当前 `model.json` 中大量复杂算法以内嵌 Python 脚本形式存在，导致：
- 算法难以在 IDE 中调试、测试和版本管理
- 相同逻辑无法被多个模型复用
- 修改算法需要重新发布整个模型文件
- 复杂脚本充斥 JSON，可读性和维护性差

本设计目标是：
1. 将复杂算法外迁到独立的 Python 脚本文件夹中
2. 在 `model.json` 中以简洁 DSL 调用外部算法
3. 支持运行时热更新，无需重启后端服务
4. 保持算法函数的纯粹性，降低不可控副作用
5. 兼容现有的 `this.variables.xxx` 等内嵌脚本写法

## 2. 核心设计原则

- **算法纯粹性**：算法包中的函数只接收干净的 `args`，不直接操作 agent 状态或调用外部 API
- **DSL 显式命名**：所有上下文访问通过显式命名空间（`this.variables`、`this.attributes`、`algo.xxx` 等），语义清晰，便于后续做 IDE 自动补全
- **适配器职责**：`runScript` 作为轻量适配层，负责组装参数、调用算法、回写结果
- **向后兼容**：保留现有的 `type: "runScript"` 结构和内嵌脚本能力，新能力作为增强选项存在

## 3. 算法包目录结构与自动注册

### 3.1 目录约定

```
algo_packages/
├── ladle_dispatcher/
│   ├── __init__.py
│   └── getCandidateLadles.py
├── steel_grade/
│   ├── __init__.py
│   └── compatibility_matrix.py
└── ...
```

### 3.2 装饰器与注册机制

算法函数通过装饰器声明元数据，启动时自动扫描注册。

```python
from agent_studio.runtime.algo import algo_function, algo_service

@algo_function(
    name="getCandidateLadles",
    package="ladle_dispatcher",
)
def get_candidate_ladles(args: dict) -> dict:
    """
    纯计算函数，只读 args，不修改任何状态。
    """
    ladles = args.get("ladles", [])
    converter_id = args.get("converterId")
    # ... 复杂筛选逻辑
    return {"candidates": candidates, "candidateCount": len(candidates)}

@algo_service(
    name="loadSteel",
    package="ladle",
)
def load_steel(args: dict) -> dict:
    """
    服务逻辑，同样只接收 args，返回结果。
    注意：这里不直接写 this.variables，而是让 runScript adapter 回写。
    """
    loaded_amount = args.get("loadedAmount")
    return {"success": True, "loadedAmount": loaded_amount}
```

### 3.3 AlgoRegistry

后端启动时执行：

```python
AlgoRegistry.scan("algo_packages/")
```

扫描器递归遍历所有 `.py` 文件，import 模块，收集所有带 `@algo_function` / `@algo_service` 装饰器的函数，建立映射表：

```
ladle_dispatcher.getCandidateLadles -> <function>
ladle.loadSteel -> <function>
```

## 4. JSON 中的 DSL 规范

### 4.1 runScript 中的可用上下文对象

在 `type: "runScript"` 的沙箱执行环境中，注入以下对象：

| 对象 | 访问示例 | 含义 |
|------|---------|------|
| `this.variables` | `this.variables.steelAmount` | 当前 agent 的运行时变量 |
| `this.attributes` | `this.attributes.capacity` | 当前 agent 的静态属性 |
| `this.services` | `this.services.moveTo(args)` | 调用本 agent 的 service |
| `this.functions` | `this.functions.calculateLoad(args)` | 调用本 agent 的 function |
| `this.rules` | `this.rules.capacityLimit` | 当前 model 的 rules 定义（只读） |
| `this.derivedProperties` | `this.derivedProperties.fillRate` | 当前 agent 的派生属性计算结果 |
| `agents.getInstance` | `agents.getInstance(id="ladle-001")` | 查询单个 agent 实例，返回 dict |
| `agents.getInstances` | `agents.getInstances(model="ladle")` | 查询多个 agent 实例，返回 list[dict] |
| `agents.getModel` | `agents.getModel(id="ladle")` | 查询 model 定义配置，返回 dict |
| `algo` | `algo.ladle_dispatcher.getCandidateLadles(args)` | 调用外部算法包函数 |
| `api` | `api.post("/path-planning/eta", data)` | 受控外部 API 客户端 |
| `emit` | `emit("ladleLoaded", payload)` | 触发事件 |
| `args` | `args.weight` | 本次调用传入的参数 |
| `payload` | `payload.converterId` | behavior 触发时的事件载荷 |

### 4.2 使用示例

#### function 调用算法

```json
"calculateLoad": {
  "title": "计算可装载量",
  "type": "runScript",
  "scriptEngine": "python",
  "script": "return algo.ladle.calculateLoad({\n    'capacity': this.attributes.capacity,\n    'steelAmount': this.variables.steelAmount,\n    'weight': args.weight\n})"
}
```

#### service 调用算法并回写状态

```json
"loadSteel": {
  "title": "向钢包装载钢水",
  "type": "runScript",
  "scriptEngine": "python",
  "rules": {
    "pre": ["refractoryLifeCheck", "capacityLimit"]
  },
  "script": "result = algo.ladle.loadSteel({\n    'capacity': this.attributes.capacity,\n    'steelAmount': this.variables.steelAmount,\n    'weight': args.weight,\n    'temperature': args.temperature,\n    'steelGrade': args.steelGrade,\n    'carbonContent': args.get('carbonContent', 0)\n})\nif result['success']:\n    this.variables.steelAmount = result['totalAmount']\n    this.variables.temperature = args.temperature\n    this.variables.steelGrade = args.steelGrade\nreturn result",
  "permissions": {
    "roles": ["converter_operator", "system"]
  }
}
```

#### behavior 调用算法

```json
"captureConverterTarget": {
  "title": "记录转炉目标位置",
  "trigger": {
    "type": "event",
    "name": "beginLoad",
    "when": "payload.converterId != null"
  },
  "priority": 1,
  "actions": [
    {
      "type": "runScript",
      "scriptEngine": "python",
      "script": "this.variables.targetLocation = f'converter_{payload.converterId}'"
    }
  ]
}
```

### 4.3 纯算法脚本示例

```python
# algo_packages/ladle_dispatcher/__init__.py
from agent_studio.runtime.algo import algo_function

@algo_function(name="getCandidateLadles", package="ladle_dispatcher")
def get_candidate_ladles(args: dict) -> dict:
    ladles = args.get("ladles", [])
    converter_id = args.get("converterId")
    steel_grade = args.get("steelGrade")
    min_temp = args.get("minRequiredTemp", 1500)
    safety_margin = args.get("safetyMargin", 20)

    candidates = []
    for ladle in ladles:
        # 硬过滤逻辑...
        candidates.append({...})

    return {
        "candidates": candidates,
        "candidateCount": len(candidates),
    }
```

## 5. 安全边界与权限控制

根据 `runScript` 所在的调用来源，沙箱注入不同权限的上下文对象：

### 5.1 functions 中

| 对象 | 权限 |
|------|------|
| `this.variables` | 只读 |
| `this.attributes` | 只读 |
| `this.derivedProperties` | 只读 |
| `this.rules` | 只读 |
| `this.functions` | 允许调用（只读链） |
| `this.services` | ❌ 禁止，抛出 `ImmutableContextError` |
| `emit` | ❌ 禁止 |
| `agents.*` | 允许 |
| `algo.*` | 允许 |
| `api.*` | 允许 |

### 5.2 services / behaviors 中

| 对象 | 权限 |
|------|------|
| `this.variables` | 可读写 |
| `this.attributes` | 只读 |
| `this.services` | 允许调用 |
| `this.functions` | 允许调用 |
| `emit` | 允许 |
| `agents.*` | 允许 |
| `algo.*` | 允许 |
| `api.*` | 允许 |

## 6. 热更新机制

后端通过 `watchdog` 或轮询监控 `algo_packages/` 目录下的 `.py` 文件变更。

### 6.1 热更新流程

1. 检测到 `.py` 文件 mtime 变更
2. 调用 `AlgoRegistry.reload_module(path)`
3. 使用 `importlib.reload()` 重新加载 Python 模块
4. 重新扫描装饰器，更新注册表
5. 正在执行的调用不受影响（基于 Python 模块对象替换机制）

### 6.2 元数据变更处理

若修改了 `name`、`package` 等注册元数据：
- 不会影响已加载的模型实例
- 下次加载/校验 model.json 时，按最新注册表进行引用校验

## 7. 配置校验规则（新增）

### P1 校验项

1. `algo.<package>.<entrypoint>` 引用的包和入口函数必须在 `AlgoRegistry` 中存在
2. `algo` 调用出现在 `functions` 中时，若目标算法声明 `readonly=False`，允许但告警（或按策略拒绝）
3. 禁止在 `functions` 的 `runScript` 中调用 `this.services` 或 `emit`

## 8. 迁移路径

现有 `model.json` 中的内嵌脚本**无需立即迁移**，新旧机制共存。

建议迁移策略：
1. 新建 `algo_packages/<package>/` 目录
2. 将复杂算法提取为 `@algo_function` 装饰的纯函数
3. 在 `model.json` 中将原内嵌脚本替换为 `algo.xxx()` 调用 + 轻量 adapter
4. 简单脚本（如单变量赋值、事件触发）可继续保留内嵌形式

## 9. 与现有代码的对齐

当前项目已有的 `scripts/ladle_dispatcher/getCandidateLadles.py` 已经实践了"外部脚本 + 纯计算函数 + ctx 注入"的模式。本设计在此基础上：
- 将 `ctx` 中的 `this`/`runtime` 能力拆分为更明确的 DSL 入口
- 去掉算法函数对 `ctx` 的依赖，使其更纯粹
- 增加自动注册和热更新机制
- 规范 JSON 中的调用方式

## 10. 未决问题（后续迭代）

1. `api` 客户端的白名单机制（允许访问的 URL/服务列表）
2. `agents.getInstance` 返回的 dict 是否包含 `bindings` 等实例敏感字段
3. 算法包的版本管理（是否支持多版本并存）
4. `algo_function` 与 `algo_service` 的区别是否需要保留，或统一为单一装饰器
