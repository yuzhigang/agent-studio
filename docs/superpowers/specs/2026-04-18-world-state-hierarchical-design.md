# World State 层级化设计文档

> 日期：2026-04-18  
> 关联计划：`docs/superpowers/plans/2026-04-17-instance-world-state.md`

## 1. 背景与问题

当前计划中的 `WorldState` 聚合器返回摊平结构：

```python
{
    "ladle-001": {"model_name": "ladle", "state": {...}, "temperature": 1500},
    "ladle-002": {"model_name": "ladle", "state": {...}, "temperature": 1600},
}
```

问题：
- 对外接口以 `instance_id` 为键，消费方需要二次按 `model_name` 分组才能做模型级分析
- `Instance.world_state` 结构与最终对外结构不一致（前者摊平，后者需要重组）
- `state` 嵌套为 `{current, enteredAt}`，消费方需额外解包

## 2. 目标

1. 运行时 `WorldState.snapshot()` 输出按 `model_name` 分组的层级结构
2. `Instance.world_state` 与对外结构保持一致的字段划分（元数据 + 业务快照）
3. `state` 摊平，`enteredAt` 改为 `updated_at`
4. 持久化时 `instance` snapshot 中的 `world_state` 保留此结构化信息

## 3. 设计

### 3.1 `Instance.world_state` 结构

每个 instance 维护一个 `world_state` dict，包含四部分：

| 字段 | 来源 | 说明 |
|------|------|------|
| `id` | `instance.instance_id` | 实例唯一标识 |
| `state` | `instance.state["current"]` | 当前状态字符串，摊平提取 |
| `updated_at` | `instance.state["enteredAt"]` | 状态最后更新时间（原 `enteredAt` 改名） |
| `lifecycle_state` | `instance.lifecycle_state` | 生命周期状态 |
| `snapshot` | `variables`/`attributes`/`derivedProperties` 中 `audit: true` 字段 | 可审计的业务属性投影 |

```python
{
    "id": "ladle-001",
    "state": "idle",
    "updated_at": "2024-01-01T00:00:00Z",
    "lifecycle_state": "active",
    "snapshot": {
        "temperature": 1500,
        "capacity": 300,
        "loadRatio": 0.75
    }
}
```

### 3.2 `Instance` 的 `snapshot` 与 `world_state`

`Instance` 持有 `snapshot` dict 和 `_audit_fields` 缓存，在已知变更点由 `InstanceManager` 调用 `_update_snapshot()` 增量更新。`world_state` 为只读 property，动态组装元数据 + snapshot。

```python
@dataclass
class Instance:
    ...
    snapshot: dict = field(default_factory=dict, repr=False)
    _audit_fields: dict = field(default_factory=dict, repr=False)

    def _update_snapshot(self) -> dict:
        if not self._audit_fields and self.model:
            for name, defn in (self.model.get("variables") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "variables"
            for name, defn in (self.model.get("attributes") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "attributes"
            for name, defn in (self.model.get("derivedProperties") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "derived"

        self.snapshot = {}
        for field_name, source in self._audit_fields.items():
            if source == "variables":
                self.snapshot[field_name] = copy.deepcopy(self.variables.get(field_name))
            elif source == "attributes":
                self.snapshot[field_name] = copy.deepcopy(self.attributes.get(field_name))
            elif source == "derived":
                self.snapshot[field_name] = copy.deepcopy(
                    self.variables.get(field_name, self.attributes.get(field_name))
                )
        return self.snapshot

    @property
    def world_state(self) -> dict:
        return {
            "id": self.instance_id,
            "state": self.state.get("current"),
            "updated_at": self.state.get("enteredAt"),
            "lifecycle_state": self.lifecycle_state,
            "snapshot": copy.deepcopy(self.snapshot),
        }
```

### 3.3 `WorldState.snapshot()` 聚合输出

按 `model_name` 分组，返回 `dict[str, list[dict]]`：

```python
def snapshot(self) -> dict:
    result: dict[str, list[dict]] = {}
    for inst in self._im.list_by_world(self._world_id):
        if inst.lifecycle_state == "active" and inst.world_state:
            model_name = inst.model_name
            result.setdefault(model_name, []).append(copy.deepcopy(inst.world_state))
    return result
```

输出示例：

```json
{
  "ladle": [
    {
      "id": "ladle-001",
      "state": "idle",
      "updated_at": "2024-01-01T00:00:00Z",
      "lifecycle_state": "active",
      "snapshot": {
        "temperature": 1500,
        "capacity": 300,
        "loadRatio": 0.75
      }
    },
    {
      "id": "ladle-002",
      "state": "moving",
      "updated_at": "2024-01-01T01:00:00Z",
      "lifecycle_state": "active",
      "snapshot": {
        "temperature": 1600,
        "capacity": 300,
        "loadRatio": 0.80
      }
    }
  ],
  "crane": [
    {
      "id": "crane-001",
      "state": "lifting",
      "updated_at": "2024-01-01T00:30:00Z",
      "lifecycle_state": "active",
      "snapshot": {
        "loadWeight": 5000,
        "position": {"x": 10, "y": 20}
      }
    }
  ]
}
```

### 3.4 持久化层面

`instance` 持久化 dict（`InstanceManager.build_persist_dict()` 返回的用于 `instance_store.save_instance()` 的数据）中的 `world_state` 字段存储上述完整结构。

```python
def build_persist_dict(self, inst: Instance) -> dict:
    return {
        "model_name": inst.model_name,
        "model_version": inst.model_version,
        "attributes": inst.attributes or {},
        "state": inst.state or {"current": None, "enteredAt": None},
        "variables": inst.variables or {},
        "links": inst.links or {},
        "memory": inst.memory or {},
        "audit": inst.audit or {"version": 0, "updatedAt": None, "lastEventId": None},
        "lifecycle_state": inst.lifecycle_state,
        "world_state": inst.world_state or {},  # 新增：保留结构化 world_state
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
```

恢复时从 DB 读取持久化 dict，将 `world_state` 还原到 `Instance`（通过 `snapshot` 和 `world_state` property 自然呈现），无需重新计算。后续事件或脚本执行时由 `InstanceManager` 调用 `_update_snapshot()` 更新。

## 4. 与现有计划的差异对照

| 项目 | 原计划 | 本设计 |
|------|--------|--------|
| `Instance.world_state` 结构 | 摊平投影：`{model_name, state, temperature, ...}` | 结构化：`{id, state, updated_at, lifecycle_state, snapshot}` |
| `WorldState.snapshot()` 输出 | `dict[instance_id, dict]` | `dict[model_name, list[dict]]` |
| `state` 表示 | 嵌套 `{current, enteredAt}` | 摊平字符串 `"idle"` |
| 时间戳字段 | `enteredAt` | `updated_at` |
| 持久化 `world_state` | 不包含在 `instance` snapshot 中 | 包含完整 `world_state` 结构 |
| `Instance` 的 audit 数据 | 无独立属性，由 `recompute_world_state()` 全量扫描 model | `snapshot` 属性 + `_audit_fields` 缓存，增量更新 |
| `InstanceManager` 持久化方法 | `snapshot(inst)` | `build_persist_dict(inst)` |

## 5. 影响范围

### 需修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/runtime/instance.py` | 新增 `snapshot` 属性、`_audit_fields` 缓存、`_update_snapshot()` 方法；`world_state` 改为 property |
| `src/runtime/world_state.py` | `snapshot()` 改为按 `model_name` 分组 |
| `src/runtime/instance_manager.py` | `snapshot()` 重命名为 `build_persist_dict()`；在各变更点调用 `_update_snapshot()`；`_build_behavior_context` 中注入的 `world_state` 格式适配 |
| `src/runtime/world_registry.py` | `pre_publish_hook` 中调用 `_update_snapshot()` |
| `tests/runtime/test_instance.py` | 测试断言适配新结构 |
| `tests/runtime/test_world_state.py` | 测试断言适配 `dict[str, list]` 格式 |
| `tests/runtime/test_instance_manager.py` | 测试断言适配新结构 |
| `tests/runtime/test_world_registry.py` | 测试断言适配新结构 |

### Sandbox 行为上下文中的 `world_state`

`InstanceManager._build_behavior_context` 注入到 sandbox 的 `world_state` 变量将变为层级化结构。Behavior scripts 访问方式变化：

```python
# 原摊平结构
world_state["ladle-001"]["temperature"]

# 新层级结构
world_state["ladle"][0]["snapshot"]["temperature"]
```

建议同时提供一个便捷访问方式（如按 id 查找的辅助函数），避免 behavior scripts 因结构调整而大面积修改。此辅助函数作为后续增强，不在本次设计中实现。

## 6. 测试策略

1. `test_instance_world_state_structure`：验证 `world_state` property 返回结构包含 `id`、`state`、`updated_at`、`lifecycle_state`、`snapshot`
2. `test_instance_update_snapshot_caches_audit_fields`：验证首次调用 `_update_snapshot()` 时缓存 `_audit_fields`，后续增量更新
3. `test_world_state_snapshot_groups_by_model_name`：验证 `WorldState.snapshot()` 按 `model_name` 分组，返回 `dict[str, list]`
4. `test_instance_manager_persist_dict_includes_world_state`：验证 `instance_store.save_instance` 接收的 persist dict 包含 `world_state` 字段
5. `test_restore_world_preserves_world_state`：验证 restore 后 instance 的 `world_state` 与 checkpoint 时一致

## 7. 自检

- **无 TBD/TODO**：所有字段定义、行为、影响范围已明确
- **内部一致性**：`Instance.world_state` 结构与 `WorldState.snapshot()` 输出结构一致，均为 `{id, state, updated_at, lifecycle_state, snapshot}`
- **范围聚焦**：本设计仅调整 `world_state` 的数据结构，不引入新的功能或外部依赖
- **无歧义**：`state` 摊平后取 `state["current"]`，`updated_at` 取 `state["enteredAt"]`，逻辑单一
