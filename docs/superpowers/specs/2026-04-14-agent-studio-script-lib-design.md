# Agent Studio 脚本库（Script Lib）设计文档

## 1. 背景与目标

当前 `model.json` 中大量复杂逻辑以内嵌 Python 脚本形式存在，导致：
- 脚本难以在 IDE 中调试、测试和版本管理
- 相同逻辑无法被多个模型复用
- 修改脚本需要重新发布整个模型文件
- 复杂脚本充斥 JSON，可读性和维护性差

本设计目标是：
1. 将复杂脚本外迁到独立的 Python 脚本文件夹中
2. 每个 agent model 拥有独立的脚本目录，并在 `model.json` 中以简洁 DSL 调用
3. 提供全局公共脚本库，供所有 agent 共享
4. 支持运行时热更新，无需重启后端服务
5. 保持脚本函数的纯粹性，降低不可控副作用
6. 兼容现有的 `this.variables.xxx` 等内嵌脚本写法

## 2. 核心设计原则

- **脚本纯粹性**：脚本库中的函数只接收干净的 `args`，不直接操作 agent 状态或调用外部 API
- **DSL 显式命名**：所有上下文访问通过显式命名空间（`this.variables`、`this.attributes`、`lib.xxx` 等），语义清晰，便于后续做 IDE 自动补全
- **适配器职责**：`runScript` 作为轻量适配层，负责组装参数、调用脚本函数、回写结果
- **向后兼容**：保留现有的 `type: "runScript"` 结构和内嵌脚本能力，新能力作为增强选项存在
- **作用域内省略 namespace**：在当前 agent 的 `model.json` 中通过 `runScript` 调用时，可省略本 agent 的 namespace，简写为 `lib.<module>.<function>`。`libs/` 下的 Python 脚本内部作为普通 Python 函数互相调用，不通过 `lib` 代理解析。

## 3. 脚本库目录结构与自动注册

### 3.1 目录约定

```
agents/
├── ladle/
│   ├── model.json
│   └── libs/
│       ├── dispatcher.py
│       └── validator.py
├── converter/
│   ├── model.json
│   └── libs/
│       └── planner.py
└── shared/
    └── libs/
        ├── data_adapter.py
        └── common_utils.py
```

- 每个 `agents/<model>/libs/` 目录注册为 `lib.<model>` 命名空间
- `agents/shared/libs/` 目录注册为 `lib.shared` 命名空间

### 3.2 装饰器与注册机制

脚本函数统一使用 `@lib_function` 装饰器声明元数据，启动时自动扫描注册。`readonly` 参数用于标记该函数是否承诺为纯计算函数。`namespace` 为必填字段，用于校验脚本所在目录与声明的命名空间是否一致；若不一致，注册时抛出 `LibRegistrationError`。

```python
from runtime.lib import lib_function

@lib_function(
    name="getCandidates",
    namespace="ladle",
    readonly=True,
)
def get_candidates(args: dict) -> dict:
    """
    纯计算函数，只读 args，不修改任何状态。
    """
    ladles = args.get("ladles", [])
    converter_id = args.get("converterId")
    # ... 复杂筛选逻辑
    return {"candidates": candidates, "candidateCount": len(candidates)}

@lib_function(
    name="loadSteel",
    namespace="ladle",
    readonly=False,
)
def load_steel(args: dict) -> dict:
    """
    服务逻辑，同样只接收 args，返回结果。
    注意：这里不直接写 this.variables，而是让 runScript adapter 回写。
    """
    loaded_amount = args.get("loadedAmount")
    return {"success": True, "loadedAmount": loaded_amount}
```

### 3.3 LibRegistry

后端启动时执行：

```python
LibRegistry.scan("agents/")
```

扫描器递归遍历所有 `agents/<namespace>/libs/` 和 `agents/shared/libs/` 下的 `.py` 文件，import 模块，收集所有带 `@lib_function` 装饰器的函数，建立映射表：

```
ladle.dispatcher.getCandidates -> <function>
ladle.validator.checkCapacity -> <function>
shared.data_adapter.transform -> <function>
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
| `agents.getInstances` | `agents.getInstances(model="ladle")` | 查询多个 agent 实例，返回 list[dict]（当前版本无分页，返回全部） |
| `agents.getModel` | `agents.getModel(id="ladle")` | 查询 model 定义配置，返回 dict |
| `lib` | `lib.dispatcher.getCandidates(args)` | 调用当前 agent 的脚本库（省略 namespace） |
| `lib` | `lib.shared.data_adapter.transform(args)` | 调用公共脚本库 |
| `lib` | `lib.ladle.dispatcher.getCandidates(args)` | 跨 scope 调用其他 agent 的脚本库 |
| `api` | `api.post("/path-planning/eta", data)` | 受控外部 API 客户端 |
| `emit` | `emit("ladleLoaded", payload)` | 触发事件 |
| `args` | `args.weight` | 本次调用传入的参数 |
| `payload` | `payload.converterId` | behavior 触发时的事件载荷 |

### 4.2 作用域内省略 namespace

在当前 agent 的 `model.json` 中通过 `runScript` 调用时，可省略本 agent 的 namespace：

```python
# 以下两种写法在 ladle 的 model.json runScript 中等价
lib.dispatcher.getCandidates(args)
lib.ladle.dispatcher.getCandidates(args)
```

**注意**：`agents/<model>/libs/` 下的 Python 脚本内部，函数之间直接通过普通 Python `import` 调用即可，不经过 `lib` 代理对象解析。

公共库和跨 scope 调用必须显式写出完整路径：

```python
lib.shared.data_adapter.transform(args)
lib.converter.planner.resolvePath(args)
```

### 4.3 使用示例

#### function 调用脚本

```json
"getCandidateLadles": {
  "title": "查询可用钢包候选集",
  "type": "runScript",
  "scriptEngine": "python",
  "script": "return lib.dispatcher.getCandidates({\n    'converterId': args.converterId,\n    'steelGrade': args.steelGrade,\n    'requiredByTime': args.requiredByTime,\n    'ladles': agents.getInstances(model='ladle'),\n    'safetyMargin': this.attributes.temperatureSafetyMargin\n})"
}
```

#### service 调用脚本并回写状态

```json
"loadSteel": {
  "title": "向钢包装载钢水",
  "type": "runScript",
  "scriptEngine": "python",
  "rules": {
    "pre": ["refractoryLifeCheck", "capacityLimit"]
  },
  "script": "result = lib.loadSteel({\n    'capacity': this.attributes.capacity,\n    'steelAmount': this.variables.steelAmount,\n    'weight': args.weight,\n    'temperature': args.temperature,\n    'steelGrade': args.steelGrade,\n    'carbonContent': args.get('carbonContent', 0)\n})\nif result['success']:\n    this.variables.steelAmount = result['totalAmount']\n    this.variables.temperature = args.temperature\n    this.variables.steelGrade = args.steelGrade\nreturn result",
  "permissions": {
    "roles": ["converter_operator", "system"]
  }
}
```

#### behavior 调用脚本

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
      "script": "target = lib.shared.dispatcher.resolveConverterLocation({'converterId': payload.converterId})\nthis.variables.targetLocation = target['location']"
    }
  ]
}
```

### 4.4 DSL 语法规范

`runScript` 的 `script` 字段是一段受限 Python 代码，其执行环境为：

- `this`、`agents`、`lib`、`api`、`emit`、`args`、`payload` 为运行时注入的代理对象或函数
- `lib.<module>.<name>(...)` 或 `lib.<namespace>.<module>.<name>(...)` 在运行时被解析为 `LibRegistry` 中对应注册的函数调用
- 其余语法为标准 Python，但 `__builtins__` 被替换为白名单子集

脚本通过 `exec()` 在受限 globals 字典中执行，不共享模块级别的全局状态。

#### __builtins__ 白名单

允许的内置对象与函数：

```python
SAFE_BUILTINS = {
    # 类型
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "chr", "complex", "dict", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max",
    "min", "next", "object", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "type", "vars", "zip",
    # 异常与工具
    "Exception", "BaseException", "RuntimeError", "ValueError", "TypeError",
    "KeyError", "IndexError", "AttributeError", "StopIteration",
    "True", "False", "None",
}
```

以下内置函数被显式移除：`open`, `eval`, `exec`, `__import__`, `compile`, `getattr`, `setattr`, `delattr`, `input`, `breakpoint`, `help`, `quit`, `exit`。

### 4.5 预置标准库

为降低脚本和 adapter 的编写成本，沙箱默认注入以下标准库模块，脚本和脚本函数中可直接引用，无需手动 `import`：

**数学计算**
- `math` — 标准数学函数（sin, cos, sqrt, ceil, floor 等）
- `random` — 随机数生成
- `statistics` — 基础统计（mean, median, stdev, variance 等）

**聚合与迭代**
- `itertools` — 迭代器工具
- `functools` — 高阶函数（reduce, partial 等）
- `operator` — 运算符函数
- `collections` — Counter, defaultdict, deque, OrderedDict 等

**数据处理**
- `json` — JSON 序列化/反序列化
- `datetime` / `time` — 日期时间处理
- `re` — 正则表达式

**字符串与工具**
- `string` — 字符串常量
- `copy` — 深拷贝与浅拷贝
- `typing` — 类型提示支持

**使用示例：**
```python
import math
avg_temp = statistics.mean([l['temperature'] for l in ladles])
```

> 注：虽然 `import` 语法被保留，但沙箱会拦截对非白名单模块的导入请求，并抛出 `ImportError`。

### 4.6 纯脚本函数示例

```python
# agents/ladle/libs/dispatcher.py
from runtime.lib import lib_function

@lib_function(name="getCandidates", namespace="ladle", readonly=True)
def get_candidates(args: dict) -> dict:
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
| `this.services` | 禁止，抛出 `ImmutableContextError` |
| `emit` | 禁止 |
| `agents.*` | 允许（`getInstance`、`getInstances`、`getModel`） |
| `lib.*` | 允许 |
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
| `lib.*` | 允许 |
| `api.*` | 允许 |

### 5.3 沙箱实现机制

`runScript` 的执行通过受限的 Python `exec()` 实现：

1. **受限 globals**：为每次执行创建独立的 `globals()` 字典，注入 `this`、`agents`、`lib`、`api`、`emit`、`args`、`payload` 等代理对象。`__builtins__` 被替换为白名单子集（移除 `open`、`eval`、`exec`、`__import__`、`compile`、`getattr` 等）
2. **代理隔离**：`this.variables` 在 `functions` 中返回 `MappingProxyType` 只读视图；在 `services`/`behaviors` 中返回可变代理，但写操作会经过审计拦截器
3. **agents 返回深拷贝**：`agents.getInstance`、`agents.getInstances`、`agents.getModel` 均返回对应 dict 的 `deepcopy`，防止脚本修改其他 agent 的内部状态或 model 定义
4. **lib 调用拦截**：`lib` 对象通过自定义 `__getattr__` 链实现，最终调用由 `LibRegistry` 分发，不经过 Python 的模块导入机制

## 6. 热更新机制

后端通过 `watchdog` 或轮询监控 `agents/**/libs/` 目录下的 `.py` 文件变更。

### 6.1 热更新流程

1. 检测到 `.py` 文件 mtime 变更
2. `LibRegistry` 对受影响模块的 namespace 加写锁
3. 使用 `importlib.reload()` 重新加载 Python 模块
4. 重新扫描装饰器，原子化地更新注册表映射
5. 释放写锁。reload 期间新发起的 `lib` 调用在锁外阻塞等待；已启动的调用继续持有旧函数对象引用并正常执行。由于 Python 的 `importlib.reload()` 本身不是线程安全的，写锁期间禁止任何对受影响模块的新调用进入。

### 6.2 元数据变更处理

若修改了 `name`、`namespace` 等注册元数据：
- 不会影响已加载的模型实例
- 下次加载/校验 model.json 时，按最新注册表进行引用校验

## 7. 配置校验规则（新增）

### P1 校验项

1. `lib.<module>.<entrypoint>` 或 `lib.<namespace>.<module>.<entrypoint>` 引用的路径必须在 `LibRegistry` 中存在
2. `lib` 调用出现在 `functions` 中时，目标脚本函数必须声明 `readonly=True`
3. `functions` 中的 `runScript` 禁止调用 `this.services` 或 `emit`——主要依靠运行时沙箱代理抛出 `ImmutableContextError` 进行拦截；配置校验阶段可做简单的字符串扫描作为辅助提示，但不强求深度 AST 分析

## 8. 迁移路径

现有 `model.json` 中的内嵌脚本**无需立即迁移**，新旧机制共存。

建议迁移策略：
1. 新建 `agents/<model>/libs/` 目录
2. 将复杂逻辑提取为 `@lib_function` 装饰的纯函数
3. 在 `model.json` 中将原内嵌脚本替换为 `lib.xxx()` 调用 + 轻量 adapter
4. 简单脚本（如单变量赋值、事件触发）可继续保留内嵌形式

对于原有 `algo_packages/` 下的脚本，迁移步骤：
1. 将 `algo_packages/<package>/` 移动或复制到对应 `agents/<model>/libs/` 目录
2. 将 `@algo_function` 替换为 `@lib_function`
3. 将装饰器中的 `namespace` 参数值设为对应 agent model 的 ID
4. 将 `model.json` 中的 `algo.xxx` 调用替换为 `lib.xxx`

## 9. 错误处理约定

### 9.1 脚本未找到

当 `lib.xxx` 无法在 `LibRegistry` 中解析时：
- 校验阶段：抛出 `LibValidationError`，阻止 model 加载
- 运行时：抛出 `LibNotFoundError`，返回 `{"success": False, "error": "LIB_NOT_FOUND", "details": "..."}`

### 9.2 脚本执行异常

脚本函数内部抛出的 Python 异常：
- 由 `LibRegistry` 捕获并包装为 `LibExecutionError`
- 返回结构：`{"success": False, "error": "LIB_EXECUTION_FAILED", "message": str(e), "traceback": "..."}`

### 9.3 DSL 脚本异常

`runScript` 中的语法错误或运行时异常：
- `SyntaxError` / `NameError`：包装为 `ScriptExecutionError`，包含行号信息，返回结构：`{"success": False, "error": "SCRIPT_EXECUTION_FAILED", "message": str(e), "line": ...}`
- 越权操作（如 `functions` 中调用 `this.services.moveTo`）：抛出 `ImmutableContextError`，返回结构：`{"success": False, "error": "IMMUTABLE_CONTEXT", "message": "..."}`
- 默认行为：阻断当前调用链，记录审计日志
