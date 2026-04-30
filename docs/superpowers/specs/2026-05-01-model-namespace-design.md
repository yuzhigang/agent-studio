# Model Namespace Design

> 所有 modelId 强制包含 namespace，文件系统路径固定为两级，彻底消除同名模型冲突。

- **Status**: Draft
- **Date**: 2026-05-01
- **Author**: Claude

## Problem

当前 `ModelResolver` 使用 `rglob` 递归查找 `*/{modelId}/model` 目录，导致同名模型在不同命名空间下会静默冲突（第一个匹配 wins，其余被忽略）。`sync-models` 命令同样受此问题影响，无法区分 `logistics/ladle` 和 `steel/ladle`。

此外，旧的 rglob 查找策略：
- 性能随 agents 目录深度线性下降
- 无法保证查找结果的可预测性
- 给模型组织带来隐性约束

## Design

### Principle

**所有 modelId 强制包含 namespace。** 格式固定为：

```
namespace.modelName
```

- `namespace`：单层目录名，**不能包含点号**
- `modelName`：模型标识，**可以包含点号**
- modelId **必须**包含至少一个点号，否则视为非法

### modelId 解析

```python
def split_model_id(model_id: str) -> tuple[str, str]:
    """Split model_id into (namespace, model_name).

    Raises ValueError if model_id contains no dot or empty parts.
    """
    if "." not in model_id:
        raise ValueError(f"modelId must contain namespace: {model_id}")
    namespace, model_name = model_id.split(".", 1)
    if not namespace:
        raise ValueError(f"namespace must not be empty: {model_id}")
    if not model_name:
        raise ValueError(f"model_name must not be empty: {model_id}")
    if "." in namespace:
        raise ValueError(f"namespace must not contain dot: {namespace}")
    return namespace, model_name
```

**示例**：

| modelId | namespace | model_name | 是否合法 |
|---------|-----------|------------|---------|
| `logistics.ladle` | `logistics` | `ladle` | 是 |
| `logistics.sensor.v2` | `logistics` | `sensor.v2` | 是 |
| `core.player` | `core` | `player` | 是 |
| `ladle` | — | — | **否**（缺少 namespace） |
| `a.b.c.ladle` | `a` | `b.c.ladle` | 是 |
| `logistics.steel.ladle` | `logistics` | `steel.ladle` | 是 |

### 文件系统映射

modelId 与文件系统路径一一对应，**固定为两级目录**：

```
agents/{namespace}/{model_name}/model/
```

**示例**：

| modelId | 文件系统路径 |
|---------|-------------|
| `logistics.ladle` | `agents/logistics/ladle/model/` |
| `logistics.sensor.v2` | `agents/logistics/sensor.v2/model/` |
| `core.player` | `agents/core/player/model/` |

**注意**：`model_name` 本身可以包含点号（如 `sensor.v2`），因此目录名可以是 `sensor.v2`，这在主流文件系统上完全合法。

### 查找逻辑（精确路径，无 rglob）

`_find_model_dir` 从递归查找改为**精确路径查找**：

```python
def _find_model_dir(root: Path, model_id: str) -> Path | None:
    """Exact-path lookup: root/{namespace}/{model_name}/model"""
    namespace, model_name = split_model_id(model_id)
    exact = root / namespace / model_name / "model"
    return exact if exact.is_dir() else None
```

**删除所有 rglob 查找逻辑**：
- 不再递归扫描整个 agents 目录
- 不再存在"第一个匹配 wins"的歧义
- 查找时间从 O(目录树大小) 降为 O(1)

### 复制到世界

`ensure()` 复制模板到世界时，保留 namespace 结构：

```
global:  agents/logistics/ladle/model/
world:   worlds/demo/agents/logistics/ladle/model/
```

```python
def _copy_from_template(self, template_model_dir: Path, global_root: Path) -> None:
    """Copy model/ and libs/ from template agent dir to world agents/."""
    template_agent_dir = template_model_dir.parent
    rel_path = template_agent_dir.relative_to(global_root)  # "logistics/ladle"
    world_target = self.world_dir / "agents" / rel_path
    ...
```

### sync-models 发现逻辑

`sync_models` 的模型发现从 `rglob("*/model")` 改为**按 namespace 目录遍历**：

```python
def discover_models(root: Path) -> dict[str, Path]:
    """Discover all models under root, keyed by modelId."""
    models: dict[str, Path] = {}
    for ns_dir in root.iterdir():
        if not ns_dir.is_dir():
            continue
        namespace = ns_dir.name
        if "." in namespace or namespace == "shared":
            continue
        for model_dir in ns_dir.iterdir():
            if not model_dir.is_dir():
                continue
            if not (model_dir / "model").is_dir():
                continue
            model_name = model_dir.name
            model_id = f"{namespace}.{model_name}"
            models[model_id] = model_dir / "model"
    return models
```

- 只遍历 `agents/` 下的直接子目录作为 namespace
- 每个 namespace 下的直接子目录作为 model_name
- `shared/` 目录作为特殊目录单独处理（shared/libs）

## Architecture Changes

### 1. ModelResolver

- `split_model_id()`: 新增，统一解析入口
- `_find_model_dir()`: 删除 rglob，改为精确路径
- `resolve()`: 调用新的 `_find_model_dir`
- `ensure()`: 逻辑不变，但依赖新的 `_find_model_dir`

### 2. WorldRegistry

- `model_loader` 接收的 modelId 现在带 namespace，直接传入 `resolver.ensure(modelId)`
- `agent_namespace_resolver` 中解析 namespace 时，使用 `split_model_id()`

### 3. InstanceLoader

- 扫描 `instance.yaml` 中的 `modelId` 字段，现在可以包含点号
- 无 namespace 的旧 modelId 会导致 `load_world()` 报错（`ValueError`）

### 4. 行为脚本

- 行为脚本中的 `model_loader("logistics.ladle")` 调用现在解析为带 namespace 的 modelId
- 旧的无 namespace 调用 `model_loader("ladle")` 会在 `split_model_id` 阶段抛出异常

### 5. sync-models CLI

- 模型发现改为按 namespace 遍历
- 输出中的 modelId 显示为 `namespace.model_name`
- 冲突检测按 qualified modelId 进行，不再跨 namespace 误判

## Error Handling

| 场景 | 行为 |
|------|------|
| modelId 无点号 | `ValueError: modelId must contain namespace` |
| modelId 以点号开头或结尾（如 `.ladle`、`logistics.`） | `ValueError: namespace/model_name must not be empty` |
| namespace 含点号 | `ValueError: namespace must not contain dot` |
| `resolve()` 或 `ensure()` 收到无效 modelId | 直接抛出 `ValueError`，不会返回 `None` |
| 精确路径不存在 | `_find_model_dir` 返回 `None` → `ensure()` 继续查找全局模板 |
| 全局模板也不存在 | `ModelNotFoundError` |
| 旧的无 namespace 模型目录 | 不被识别，需要手动迁移 |

## Migration Guide

旧的无 namespace 模型需要迁移：

**迁移前**：
```
agents/ladle/model/
agents/heartbeat/model/
```

**迁移后**：
```
agents/core/ladle/model/
agents/core/heartbeat/model/
```

所有引用这些模型的 `instance.yaml` 也需要更新：

```yaml
# 迁移前
modelId: ladle

# 迁移后
modelId: core.ladle
```

**迁移脚本建议**：
```python
def migrate_models(agents_dir: Path, default_ns: str = "core"):
    """将旧的无 namespace 模型迁移到 default_ns 下。"""
    for item in agents_dir.iterdir():
        if not item.is_dir():
            continue
        if (item / "model").is_dir():
            # 这是旧的无 namespace 模型
            target = agents_dir / default_ns / item.name
            target.parent.mkdir(parents=True, exist_ok=True)
            item.rename(target)
```

## Testing

### ModelResolver 单元测试

1. `split_model_id("logistics.ladle")` → `("logistics", "ladle")`
2. `split_model_id("logistics.sensor.v2")` → `("logistics", "sensor.v2")`
3. `split_model_id("ladle")` → `ValueError`
4. `split_model_id("a.b.c.ladle")` → `("a", "b.c.ladle")`
5. `_find_model_dir(agents, "logistics.ladle")` → 精确路径 `agents/logistics/ladle/model`
6. `_find_model_dir(agents, "logistics.ladle")` → 不触发 rglob
7. `resolve("logistics.ladle")` 在 world-private 下精确查找
8. `ensure("logistics.ladle")` 从全局精确复制到世界
9. 同名模型不同 namespace：`logistics.ladle` 和 `steel.ladle` 互不冲突

### sync-models 测试

10. 发现 `agents/logistics/ladle/model/` → modelId = `logistics.ladle`
11. 发现 `agents/steel/ladle/model/` → modelId = `steel.ladle`
12. `sync-models` 输出中两个 `ladle` 显示为不同的 modelId

### InstanceLoader 测试

13. `instance.yaml` 中 `modelId: logistics.ladle` 正确解析
14. `instance.yaml` 中 `modelId: ladle` 导致 `load_world()` 失败并报错

## Files to Change

| File | Change |
|------|--------|
| `src/runtime/model_resolver.py` | 新增 `split_model_id()`，重写 `_find_model_dir()` 为精确路径 |
| `src/runtime/world_registry.py` | `model_loader` 和 `agent_namespace_resolver` 适配带 namespace 的 modelId |
| `src/runtime/instance_loader.py` | `scan()` 可能需要调整 `_agent_namespace_for` 的语义 |
| `src/cli/main.py` | `sync_models` 模型发现改为按 namespace 遍历，modelId 提取逻辑更新 |
| `tests/runtime/test_model_resolver.py` | 更新测试用例，新增 namespace 相关测试 |
| `tests/runtime/test_instance_loader.py` | 更新 fixture 中的 modelId 为带 namespace 格式 |
| `tests/cli/test_main.py` | sync-models 测试用例更新（带 namespace 的 modelId） |

## Non-Goals

- 不自动迁移旧的无 namespace 模型（手动迁移，一次性操作）
- 不支持 namespace 嵌套（`a.b.ladle` 中 `a` 是 namespace，`b.ladle` 是 modelName）
- 不改数据库 schema（modelId 仍存为字符串）
- 不改 HTTP API 路径或参数名（只是 modelId 的值变了）
