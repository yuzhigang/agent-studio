# Lib Namespace 与运行时装配设计文档

> 版本：v1.0
> 日期：2026-04-26

## 1. 背景

当前 `runtime.lib` 已经具备以下几个基本构件：

- `LibRegistry`：扫描并注册 `@lib_function`
- `SandboxExecutor`：为行为脚本提供受限执行环境
- `LibProxy`：为脚本中的 `lib.xxx.yyy(...)` 提供动态解析

但这一层仍有几个关键问题需要统一：

- agent-specific libs 的 namespace 已经收紧为 `group.agent`，但运行时默认 namespace 还没有完全和脚本所属 agent 路径对齐。
- shared libs 与 agent libs 的边界需要继续明确，避免后续把 agent libs 变成全局服务定位器。
- `LibRegistry`、`SandboxExecutor`、`LibProxy` 的运行时装配需要形成闭环，避免只在测试里成立、在真实 world load 中缺失。

本设计的目标是把 libs 机制收敛为一套稳定的运行时规则：

- 脚本默认只调用自己所属 agent 的 libs
- shared 是唯一公共 lib namespace
- cross-agent 直接调用默认禁止
- `LibRegistry` / `SandboxExecutor` / `LibProxy` 都由同一条 world load 装配链注入

## 2. 目标

### 2.1 目标

- 让 agent-specific lib namespace 固定来自 agent 的目录路径，而不是从 `modelId` 或 `model_name` 推断。
- 让脚本默认 namespace 与脚本所属 agent 的 namespace 完全一致。
- 让 `shared` 成为唯一公共 lib namespace。
- 让 runtime 在 world load 时完成 `LibRegistry -> SandboxExecutor -> LibProxy` 的闭环装配。
- 明确禁止 cross-agent direct lib call。

### 2.2 非目标

- 本次不把 libs 扩展成通用 RPC/service 框架。
- 本次不引入跨 worker 的 lib 调用能力。
- 本次不定义新的 DSL 语法，只收口现有 `lib.xxx.yyy(...)` 和 `import shared-module` 的行为。

## 3. 核心原则

- namespace 来源唯一：来自 agent 目录路径。
- shared 与 agent libs 分层：shared 是公共能力，agent libs 是 agent 内部能力。
- 默认就近：脚本默认只调用自己所属 agent 的 libs。
- 显式公共：共享能力必须显式经过 `shared` 暴露。
- 禁止隐式耦合：agent 之间不能直接通过 libs 相互调用。

## 4. Namespace 规则

### 4.1 注册 namespace

`LibRegistry.scan()` 的注册 namespace 规则如下：

- `agents/shared/libs/*.py`
  - namespace 固定为 `shared`

- `agents/<group>/<agent>/libs/*.py`
  - namespace 固定为 `<group>.<agent>`

示例：

- `agents/shared/libs/api.py`
  - `shared.api.echo`

- `agents/logistics/ladle/libs/dispatcher.py`
  - `logistics.ladle.dispatcher.get_candidates`

- `agents/roles/ladle_dispatcher/libs/ladle.py`
  - `roles.ladle_dispatcher.ladle.get_candidates`

### 4.2 默认 namespace

脚本执行时，`LibProxy.default_namespace` 不从 `modelId` 或 `model_name` 推断。

它必须来自：

- 当前脚本所属 agent 的目录身份

也就是说：

- 如果脚本来自 `agents/logistics/ladle/...`
  - 默认 namespace 为 `logistics.ladle`

- 如果脚本来自 `agents/roles/ladle_dispatcher/...`
  - 默认 namespace 为 `roles.ladle_dispatcher`

### 4.3 shared namespace

`shared` 不参与默认 namespace 推断。

它始终只作为显式公共 namespace 存在：

- `lib.shared.api.echo(...)`
- `import api`

## 5. 使用规则

### 5.1 当前脚本默认访问自己所属 agent 的 libs

脚本中：

```python
lib.dispatcher.get_candidates(...)
```

其实际解析为：

```python
<当前脚本所属 agent namespace>.dispatcher.get_candidates(...)
```

### 5.2 shared 是唯一允许显式公共访问的 namespace

以下是合法调用：

```python
lib.shared.api.echo(...)
```

```python
import api
result = api.echo(...)
```

### 5.3 禁止 cross-agent direct lib call

以下调用默认禁止：

```python
lib.logistics.ladle.dispatcher.get_candidates(...)
lib.machines.converter.planner.plan(...)
```

如果当前脚本不属于对应 agent，就必须报错。

cross-agent 复用只有两条正路：

- 提升为 `shared`
- 通过事件 / message / service 机制交互

## 6. 运行时装配闭环

### 6.1 WorldRegistry 负责装配

`WorldRegistry.load_world()` 负责创建并装配：

- `LibRegistry`
- `SandboxExecutor`
- `InstanceManager`

推荐流程：

1. 定位当前 world 的 `agents/` 根目录
2. 创建 `LibRegistry`
3. 执行 `registry.scan(world_agents_dir)`
4. 创建 `SandboxExecutor(registry=registry)`
5. 创建 `InstanceManager(..., sandbox_executor=sandbox_executor, ...)`
6. 将 `registry` 保存在 bundle 中，供后续调试、热重载或 watcher 使用

### 6.2 InstanceManager 只消费 namespace，不推断 namespace

`InstanceManager` 不再自己猜测：

- 默认 namespace 是什么
- 它是否等于 `model_name`

它的职责只是：

- 在构建行为上下文时，根据“当前实例所属 agent namespace”创建 `LibProxy`

也就是：

```python
LibProxy(
    default_namespace=<当前实例所属 agent namespace>,
    registry=<world-level registry>,
    lib_context=...,
)
```

### 6.3 SandboxExecutor 与 LibProxy 使用同一个 registry

shared import 和 `lib.*` 调用必须共享同一个 `LibRegistry`：

- `SandboxExecutor(registry=registry)`
- `LibProxy(registry=registry, ...)`

这样：

- `import api`
- `lib.shared.api.echo(...)`
- `lib.dispatcher.get_candidates(...)`

都基于同一份注册表工作，不会出现测试里成立、运行时却不一致的情况。

## 7. 脚本所属 agent namespace 的来源

不新增 `libNamespace` 字段。

脚本默认 namespace 直接从脚本所属 agent 路径获取。

也就是说：

- 行为脚本属于哪个 agent
- 它的 `lib.*` 默认就解析到哪个 agent 的 libs namespace

这个信息可以作为 runtime metadata 在 world load / instance create 阶段带入：

- 不需要暴露成业务 schema 新字段
- 但必须是运行时显式可用的信息

## 8. LibRegistry 细节约束

### 8.1 注册键格式

最终注册键统一为：

```text
<namespace>.<module>.<function>
```

其中：

- `namespace`
  - `shared`
  - 或 `<group>.<agent>`

- `module`
  - `@lib_function(module=...)` 指定的 module
  - 否则默认取 `py_file.stem`

- `function`
  - `@lib_function(name=...)` 指定的 name
  - 否则默认取原始函数名

### 8.2 reload 语义

`reload_module()` 删除旧键时，必须按实际注册前缀删除，而不是只按 `py_file.stem`。

也就是说，如果某个 lib 用了：

```python
@lib_function(name="getItems", module="dao")
```

那么 reload 时必须删除：

- `namespace.dao.*`

而不是只删除：

- `namespace.<file_stem>.*`

否则会留下陈旧注册项。

## 9. Sandbox 规则

### 9.1 shared import 只暴露 shared modules

`SandboxExecutor` 只把 shared libs 暴露为 importable modules：

- `import api`
- `import utils`

agent-specific libs 不通过 Python import 暴露，只通过 `lib.*` 访问。

### 9.2 shared import 命名需要避开标准库冲突

shared module 名不得与常用标准库或预加载模块重名，例如：

- `json`
- `time`
- `math`
- `re`

否则在 sandbox 中会产生 import 遮蔽风险。

如果未来确实需要更强隔离，可以考虑把 shared import 统一收敛为：

- `import shared_api`
- `import shared_utils`

但本次先通过命名约束解决，不额外引入新 import 语法。

## 10. 测试要求

至少覆盖以下场景：

- `LibRegistry.scan()` 会把 agent libs 注册成 `group.agent.module.function`
- 同名 agent 位于不同 group 下时不会互相覆盖
- `LibProxy(default_namespace=<group.agent>)` 能解析本 agent libs
- `LibProxy` 显式访问 `lib.shared.xxx.yyy(...)` 合法
- `LibProxy` 显式访问其他 agent libs 会报错
- `SandboxExecutor(registry=registry)` 能 `import` shared modules
- `SandboxExecutor` 不能 `import` agent-specific libs
- world load 后行为脚本运行时，`lib.*` 在真实 runtime 路径中可用，不只是测试里手工构造可用
- `reload_module()` 对带 `module=` 覆盖的 lib 能正确替换旧键

## 11. 结论

这套设计最终把 shared 和 agent-specific libs 的边界收敛成：

- `shared`
  - 公共能力层
  - 所有 agent 可显式使用

- `group.agent`
  - agent 内部脚本能力层
  - 默认只供自己所属 agent 的脚本使用

同时把运行时闭环定成：

- `WorldRegistry` 负责 scan 和装配
- `SandboxExecutor` 和 `LibProxy` 共用同一个 registry
- 默认 namespace 来自脚本所属 agent 路径

这样 `libs` 机制就不再是“测试里成立的辅助能力”，而是一套在真实 runtime 中语义稳定、边界清晰的脚本库机制。
