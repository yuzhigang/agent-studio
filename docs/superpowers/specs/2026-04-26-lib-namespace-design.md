# Lib 命名空间与访问控制设计

## 背景

当前 `LibRegistry` 的命名空间存在几个问题：

1. 设计文档使用 `scripts/` 目录，但代码和 fixtures 实际使用 `libs/`
2. Agent namespace 仅用 agent 名（如 `ladle`），不同 group 下同名 agent 会冲突
3. `@lib_function` 的 `readonly` 参数没有被任何代码使用
4. `LibProxy` 允许跨 agent 完整路径调用（如 `lib.converter.planner.resolvePath`），缺少访问控制

## 目标

- 统一目录约定为 `libs/`
- 注册键使用 `group.agent` 避免冲突
- 沙箱内只允许本 agent 和 shared 的 lib 调用
- 移除未使用的 `readonly` 参数

## 架构

### 目录结构

```
agents/
├── shared/
│   └── libs/
│       ├── api.py
│       └── utils.py
├── logistics/
│   └── ladle/
│       └── libs/
│           └── dispatcher.py
└── machines/
    └── converter/
        └── libs/
            └── planner.py
```

- 每个 `agents/<group>/<agent>/libs/` 目录下的 `.py` 文件注册为 `<group>.<agent>` namespace
- `agents/shared/libs/` 目录下的 `.py` 文件注册为 `shared` namespace

### 注册键格式

| 来源 | 注册键 |
|------|--------|
| `agents/shared/libs/api.py` 中的 `@lib_function(name="echo")` | `shared.api.echo` |
| `agents/logistics/ladle/libs/dispatcher.py` 中的 `@lib_function(name="getCandidates")` | `logistics.ladle.dispatcher.getCandidates` |

### 沙箱内调用规则

`LibProxyNode.__call__` 只接受两种输入格式：

1. **省略 namespace（本 agent）**：`lib.<module>.<name>(args)`
   - `self._path` 长度为 2
   - 使用 `default_namespace` 补全为 `{group}.{agent}.{module}.{name}`
   - 示例：`lib.dispatcher.getCandidates(args)` → 解析为 `logistics.ladle.dispatcher.getCandidates`

2. **shared 库**：`lib.shared.<module>.<name>(args)`
   - `self._path` 长度为 3，且第一段为 `shared`
   - 直接使用 `shared.{module}.{name}`
   - 示例：`lib.shared.api.echo(args)` → 解析为 `shared.api.echo`

**其他任何写法都抛 `LibNotFoundError`**：
- `lib.logistics.ladle.dispatcher.getCandidates(args)` → ❌ 不允许显式完整路径
- `lib.machines.converter.planner.resolvePath(args)` → ❌ 跨 agent 调用被拒绝

### 访问控制伪代码

```python
def __call__(self, *args, **kwargs):
    if len(self._path) < 2:
        raise LibNotFoundError("incomplete path")

    if len(self._path) == 2:
        # 本 agent 简写
        if not self._default_namespace:
            raise LibNotFoundError("no default namespace")
        candidates = [f"{self._default_namespace}.{self._path[0]}.{self._path[1]}"]
    elif len(self._path) == 3 and self._path[0] == "shared":
        # shared 库
        candidates = [".".join(self._path)]
    else:
        raise LibNotFoundError("cross-agent lib calls are not allowed")

    # 查找并执行
    ...
```

## `@lib_function` 变更

移除 `readonly` 参数：

```python
def lib_function(*, name: str, namespace: str | None = None):
    def decorator(func):
        func._lib_meta = {
            "name": name,
            "namespace": namespace,
            "entrypoint": func.__name__,
            "func": func,
        }
        return func
    return decorator
```

所有 fixture 中的 `@lib_function(readonly=True)` 同步移除 `readonly=True`。

## `LibRegistry.scan` 变更

```python
# 旧：namespace = agent_dir.name
# 新：
namespace = f"{group_dir.name}.{agent_dir.name}"
```

## `LibRegistry.reload_module` 变更

```python
# 旧：namespace = parts[1]  # agent name
# 新：
namespace = f"{parts[0]}.{parts[1]}"  # group.agent
```

## 错误处理

- 跨 agent 调用：`LibNotFoundError`，details = `"cross-agent lib calls are not allowed"`
- 完整路径显式写出本 agent：`LibNotFoundError`，同上（统一错误信息，避免信息泄露）
- 不存在的函数：`LibNotFoundError`，details = `"not registered"`

## 测试覆盖

- `test_lib_omitted_namespace` — 2 段调用，default_namespace 补全
- `test_lib_shared_namespace` — `lib.shared.xxx` 调用
- `test_lib_cross_agent_rejected` — 跨 agent 调用抛错
- `test_lib_full_path_rejected` — 显式完整路径抛错
- `test_registry_scan_uses_group_agent_namespace` — 注册键包含 group
- `test_reload_module_uses_group_agent_namespace` — reload 使用 group.agent
