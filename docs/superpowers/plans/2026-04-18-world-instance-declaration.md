# World 静态实例声明加载实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现世界目录下 `agents/**/instances/*.instance.yaml` 静态实例声明的自动扫描、模型解析和实例创建。

**Architecture:** 新增 `ModelResolver`（模型目录解析）和 `InstanceLoader`（声明扫描）两个独立组件，`WorldRegistry` 在加载流程中串接它们，在 `restore_world` 之前完成静态实例创建，并给 `InstanceManager` 注入 `model_loader` 以支持懒加载。

**Tech Stack:** Python 3.13, pathlib, yaml, pytest

---

## 文件变更图

| 文件 | 动作 | 责任 |
|------|------|------|
| `src/runtime/model_resolver.py` | 新建 | 按 modelId 搜索世界 `agents/` + 全局路径，返回 `model/` 目录 |
| `src/runtime/instance_loader.py` | 新建 | 扫描世界 `agents/**/instances/*.instance.yaml` |
| `src/runtime/world_registry.py` | 修改 | 接入 resolver + loader，在 restore 之前创建实例，注入 model_loader |
| `tests/runtime/test_model_resolver.py` | 新建 | ModelResolver 单元测试 |
| `tests/runtime/test_instance_loader.py` | 新建 | InstanceLoader 单元测试 |
| `tests/runtime/test_world_registry_instance_loading.py` | 新建 | 端到端集成测试 |

---

### Task 1: ModelResolver

**Files:**
- Create: `src/runtime/model_resolver.py`
- Test: `tests/runtime/test_model_resolver.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from pathlib import Path
from src.runtime.model_resolver import ModelResolver


class TestModelResolver:
    def test_resolve_in_world_agents(self, tmp_path):
        """世界 agents/ 下找到 modelId，优先返回"""
        agents = tmp_path / "agents" / "logistics" / "ladle" / "model"
        agents.mkdir(parents=True)
        (agents / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(tmp_path), [])
        result = resolver.resolve("ladle")
        assert result == agents

    def test_resolve_prefers_world_over_global(self, tmp_path):
        """世界 agents/ 和全局路径都有同名 modelId，优先世界"""
        world_agents = tmp_path / "agents" / "logistics" / "ladle" / "model"
        world_agents.mkdir(parents=True)
        (world_agents / "index.yaml").write_text("name: ladle")

        global_dir = tmp_path / "global" / "ladle" / "model"
        global_dir.mkdir(parents=True)

        resolver = ModelResolver(str(tmp_path), [str(tmp_path / "global")])
        result = resolver.resolve("ladle")
        assert result == world_agents

    def test_resolve_falls_back_to_global(self, tmp_path):
        """世界中找不到，回退到全局路径"""
        global_dir = tmp_path / "global" / "roles" / "planner" / "model"
        global_dir.mkdir(parents=True)
        (global_dir / "index.yaml").write_text("name: planner")

        resolver = ModelResolver(str(tmp_path), [str(tmp_path / "global")])
        result = resolver.resolve("planner")
        assert result == global_dir

    def test_resolve_not_found(self, tmp_path):
        """完全找不到时返回 None"""
        resolver = ModelResolver(str(tmp_path), [])
        assert resolver.resolve("missing") is None

    def test_resolve_no_world_agents_dir(self, tmp_path):
        """世界没有 agents/ 目录时不报错，直接搜索全局"""
        global_dir = tmp_path / "global" / "crane" / "model"
        global_dir.mkdir(parents=True)

        resolver = ModelResolver(str(tmp_path), [str(tmp_path / "global")])
        assert resolver.resolve("crane") == global_dir

    def test_resolve_model_in_flat_namespace(self, tmp_path):
        """modelId 在命名空间子目录下也能找到"""
        agents = tmp_path / "agents" / "logistics" / "ladle" / "model"
        agents.mkdir(parents=True)

        resolver = ModelResolver(str(tmp_path), [])
        assert resolver.resolve("ladle") == agents

    def test_resolve_multiple_global_paths_checks_in_order(self, tmp_path):
        """多个全局路径按顺序查找"""
        path1 = tmp_path / "global1" / "a" / "model"
        path1.mkdir(parents=True)

        path2 = tmp_path / "global2" / "a" / "model"
        path2.mkdir(parents=True)

        resolver = ModelResolver(str(tmp_path), [str(tmp_path / "global1"), str(tmp_path / "global2")])
        assert resolver.resolve("a") == path1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/runtime/test_model_resolver.py -v
```

Expected: 全部 FAIL，`ModelResolver` class not found

- [ ] **Step 3: 实现 ModelResolver**

```python
"""Resolve modelId to model directory, with world agents/ taking precedence over global paths."""

from pathlib import Path


class ModelResolver:
    """Resolve a modelId to the model/ directory path.

    Search order:
    1. {world_dir}/agents/ -- recursive search for */{modelId}/model/
    2. Each global search path -- recursive search for */{modelId}/model/
    """

    def __init__(self, world_dir: str, global_paths: list[str]):
        self._world_dir = Path(world_dir)
        self._global_paths = [Path(p) for p in global_paths]

    def resolve(self, model_id: str) -> Path | None:
        """Return the model/ directory for the given modelId, or None if not found."""
        # 1. World agents/ takes precedence
        world_agents = self._world_dir / "agents"
        if world_agents.exists():
            model_dir = self._find_model_dir(world_agents, model_id)
            if model_dir is not None:
                return model_dir

        # 2. Fall back to global paths in order
        for search_path in self._global_paths:
            model_dir = self._find_model_dir(search_path, model_id)
            if model_dir is not None:
                return model_dir

        return None

    @staticmethod
    def _find_model_dir(root: Path, model_id: str) -> Path | None:
        """Recursively search root for a */{modelId}/model directory."""
        for candidate in root.rglob(f"*/{model_id}/model"):
            if candidate.is_dir():
                return candidate
        return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/runtime/test_model_resolver.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/model_resolver.py tests/runtime/test_model_resolver.py
git commit -m "feat: add ModelResolver for modelId-to-directory resolution"
```

---

### Task 2: InstanceLoader

**Files:**
- Create: `src/runtime/instance_declaration_loader.py`
- Test: `tests/runtime/test_instance_declaration_loader.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from pathlib import Path
from src.runtime.instance_loader import InstanceLoader


class TestInstanceLoader:
    def test_scan_finds_instance_files(self, tmp_path):
        """扫描 agents/**/instances/ 下的 .instance.yaml"""
        inst_dir = tmp_path / "agents" / "logistics" / "ladle" / "instances"
        inst_dir.mkdir(parents=True)
        (inst_dir / "ladle-01.instance.yaml").write_text(
            "id: ladle-01\nmodelId: ladle\n"
        )
        (inst_dir / "ladle-02.instance.yaml").write_text(
            "id: ladle-02\nmodelId: ladle\n"
        )

        decls = InstanceLoader.scan(str(tmp_path))
        assert len(decls) == 2
        ids = {d["id"] for d in decls}
        assert ids == {"ladle-01", "ladle-02"}

    def test_scan_multiple_namespaces(self, tmp_path):
        """多个命名空间下的 instances 都能扫到"""
        (tmp_path / "agents" / "logistics" / "ladle" / "instances" / "l1.instance.yaml").write_text(
            "id: l1\nmodelId: ladle\n"
        )
        (tmp_path / "agents" / "roles" / "planner" / "instances" / "p1.instance.yaml").write_text(
            "id: p1\nmodelId: planner\n"
        )

        decls = InstanceLoader.scan(str(tmp_path))
        assert len(decls) == 2

    def test_scan_no_agents_dir(self, tmp_path):
        """没有 agents/ 目录时返回空列表"""
        decls = InstanceLoader.scan(str(tmp_path))
        assert decls == []

    def test_scan_empty_agents_dir(self, tmp_path):
        """agents/ 存在但无 instances"""
        (tmp_path / "agents").mkdir()
        decls = InstanceLoader.scan(str(tmp_path))
        assert decls == []

    def test_scan_includes_source_file(self, tmp_path):
        """每个声明包含 _source_file 元信息"""
        inst_file = tmp_path / "agents" / "a" / "b" / "instances" / "x.instance.yaml"
        inst_file.parent.mkdir(parents=True)
        inst_file.write_text("id: x\nmodelId: b\n")

        decls = InstanceLoader.scan(str(tmp_path))
        assert len(decls) == 1
        assert decls[0]["_source_file"] == str(inst_file)

    def test_scan_skips_non_instance_yaml(self, tmp_path):
        """只扫描 *.instance.yaml，跳过其他 yaml"""
        inst_dir = tmp_path / "agents" / "logistics" / "ladle" / "instances"
        inst_dir.mkdir(parents=True)
        (inst_dir / "ladle-01.instance.yaml").write_text("id: l1\n")
        (inst_dir / "config.yaml").write_text("key: value\n")

        decls = InstanceLoader.scan(str(tmp_path))
        assert len(decls) == 1
        assert decls[0]["id"] == "l1"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/runtime/test_instance_declaration_loader.py -v
```

Expected: 全部 FAIL，`InstanceLoader` not found

- [ ] **Step 3: 实现 InstanceLoader**

```python
"""Scan world agents/ directory for static instance declarations."""

from pathlib import Path

import yaml


class InstanceLoader:
    """Scan a world's agents/ directory for *.instance.yaml declarations."""

    @staticmethod
    def scan(world_dir: str) -> list[dict]:
        """Recursively scan {world_dir}/agents/**/instances/*.instance.yaml.

        Returns a list of parsed declaration dicts, each with an extra
        '_source_file' key pointing to the source path.
        """
        world_path = Path(world_dir)
        agents_dir = world_path / "agents"
        declarations: list[dict] = []

        if not agents_dir.exists():
            return declarations

        for instances_dir in agents_dir.rglob("instances"):
            if not instances_dir.is_dir():
                continue
            for yaml_file in instances_dir.glob("*.instance.yaml"):
                with open(yaml_file, "r", encoding="utf-8") as f:
                    decl = yaml.safe_load(f) or {}
                decl["_source_file"] = str(yaml_file)
                declarations.append(decl)

        return declarations
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/runtime/test_instance_declaration_loader.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/instance_declaration_loader.py tests/runtime/test_instance_declaration_loader.py
git commit -m "feat: add InstanceLoader for scanning static instance declarations"
```

---

### Task 3: WorldRegistry 集成

**Files:**
- Modify: `src/runtime/world_registry.py`
- Test: `tests/runtime/test_world_registry_instance_loading.py`

- [ ] **Step 1: 写集成测试**

```python
import pytest
from src.runtime.world_registry import WorldRegistry


class TestWorldRegistryInstanceLoading:
    def test_load_world_creates_instances_from_declarations(self, tmp_path):
        """世界加载时自动创建 agents/**/instances/ 下声明的实例"""
        world_dir = tmp_path / "worlds" / "test-world"
        world_dir.mkdir(parents=True)

        # world.yaml
        (world_dir / "world.yaml").write_text(
            "world_id: test-world\nname: Test\n"
        )

        # 模型
        model_dir = world_dir / "agents" / "logistics" / "heartbeat" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "index.yaml").write_text(
            """
metadata:
  name: heartbeat
variables:
  count:
    type: number
    default: 0
attributes:
  interval:
    type: number
    default: 1000
"""
        )

        # 实例声明
        inst_dir = world_dir / "agents" / "logistics" / "heartbeat" / "instances"
        inst_dir.mkdir(parents=True)
        (inst_dir / "sensor-01.instance.yaml").write_text(
            """
id: sensor-01
modelId: heartbeat
state: idle
attributes:
  interval: 500
variables:
  count: 10
"""
        )

        registry = WorldRegistry(base_dir=str(tmp_path / "worlds"))
        bundle = registry.load_world("test-world")

        im = bundle["instance_manager"]
        inst = im.get("test-world", "sensor-01")
        assert inst is not None
        assert inst.instance_id == "sensor-01"
        assert inst.model_name == "heartbeat"
        assert inst.variables["count"] == 10          # 声明覆盖默认值
        assert inst.attributes["interval"] == 500     # 声明覆盖默认值
        assert inst.state["current"] == "idle"        # 声明的初始状态

        registry.unload_world("test-world")

    def test_load_world_skips_missing_model(self, tmp_path):
        """声明引用的 modelId 不存在时跳过，不阻断世界启动"""
        world_dir = tmp_path / "worlds" / "test-world"
        world_dir.mkdir(parents=True)
        (world_dir / "world.yaml").write_text(
            "world_id: test-world\nname: Test\n"
        )

        # 实例声明但无模型
        inst_dir = world_dir / "agents" / "x" / "instances"
        inst_dir.mkdir(parents=True)
        (inst_dir / "bad.instance.yaml").write_text(
            "id: bad\nmodelId: nonexistent\n"
        )

        registry = WorldRegistry(base_dir=str(tmp_path / "worlds"))
        bundle = registry.load_world("test-world")

        im = bundle["instance_manager"]
        assert im.get("test-world", "bad") is None
        registry.unload_world("test-world")

    def test_load_world_no_agents_dir(self, tmp_path):
        """没有 agents/ 目录时正常启动为空世界"""
        world_dir = tmp_path / "worlds" / "test-world"
        world_dir.mkdir(parents=True)
        (world_dir / "world.yaml").write_text(
            "world_id: test-world\nname: Test\n"
        )

        registry = WorldRegistry(base_dir=str(tmp_path / "worlds"))
        bundle = registry.load_world("test-world")

        im = bundle["instance_manager"]
        assert im.list_by_world("test-world") == []
        registry.unload_world("test-world")

    def test_load_world_uses_global_model_when_not_in_world(self, tmp_path):
        """世界中无模型时回退到全局模型路径"""
        world_dir = tmp_path / "worlds" / "test-world"
        world_dir.mkdir(parents=True)
        (world_dir / "world.yaml").write_text(
            "world_id: test-world\nname: Test\n"
        )

        # 全局模型
        global_model = tmp_path / "agents" / "global" / "crane" / "model"
        global_model.mkdir(parents=True)
        (global_model / "index.yaml").write_text(
            "metadata:\n  name: crane\n"
        )

        # 实例声明引用全局模型
        inst_dir = world_dir / "agents" / "logistics" / "crane" / "instances"
        inst_dir.mkdir(parents=True)
        (inst_dir / "crane-01.instance.yaml").write_text(
            "id: crane-01\nmodelId: crane\n"
        )

        registry = WorldRegistry(
            base_dir=str(tmp_path / "worlds"),
            global_model_paths=[str(tmp_path / "agents" / "global")],
        )
        bundle = registry.load_world("test-world")

        im = bundle["instance_manager"]
        inst = im.get("test-world", "crane-01")
        assert inst is not None
        assert inst.model_name == "crane"
        registry.unload_world("test-world")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: 4 FAIL，`global_model_paths` parameter not found, instances not created

- [ ] **Step 3: 修改 WorldRegistry**

```python
# src/runtime/world_registry.py
import logging
import os
from pathlib import Path

import yaml

from src.runtime.instance_loader import InstanceLoader
from src.runtime.locks.world_lock import WorldLock
from src.runtime.model_loader import ModelLoader
from src.runtime.model_resolver import ModelResolver
from src.runtime.stores.sqlite_store import SQLiteStore
from src.runtime.event_bus import EventBusRegistry
from src.runtime.instance_manager import InstanceManager
from src.runtime.scene_manager import SceneManager
from src.runtime.state_manager import StateManager
from src.runtime.world_state import WorldState

logger = logging.getLogger(__name__)


class WorldRegistry:
    def __init__(
        self,
        base_dir: str = "worlds",
        global_model_paths: list[str] | None = None,
        metric_store_factory=None,
    ):
        self._base_dir = base_dir
        self._global_model_paths = global_model_paths or []
        self._metric_store_factory = metric_store_factory
        self._loaded: dict[str, dict] = {}

    # ... _world_dir, create_world, list_worlds, get_loaded_world unchanged ...

    def load_world(self, world_id: str) -> dict:
        if world_id in self._loaded:
            return self._loaded[world_id]

        world_dir = self._world_dir(world_id)
        if not os.path.isdir(world_dir):
            raise ValueError(f"World {world_id} not found")

        yaml_path = os.path.join(world_dir, "world.yaml")
        if not os.path.exists(yaml_path):
            raise ValueError(f"World {world_id} has no world.yaml")

        world_lock = WorldLock(world_dir)
        world_lock.acquire()

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                world_yaml = yaml.safe_load(f)

            store = SQLiteStore(world_dir)
            store.save_world(world_id, world_yaml.get("config", {}))

            bus_reg = EventBusRegistry()
            world_state = WorldState(None, world_id)

            # ModelResolver for world + global model search
            resolver = ModelResolver(world_dir, self._global_model_paths)

            def model_loader(model_id: str) -> dict | None:
                model_dir = resolver.resolve(model_id)
                if model_dir is not None:
                    return ModelLoader.load(model_dir)
                return None

            im = InstanceManager(
                bus_reg,
                instance_store=store,
                model_loader=model_loader,
                world_state=world_state,
            )
            world_state._im = im

            bus = bus_reg.get_or_create(world_id)
            def world_event_hook(event_type, payload, source, scope, target):
                inst = im.get(world_id, source, scope=scope)
                if inst is not None:
                    inst._update_snapshot()
            bus.add_pre_publish_hook(world_event_hook)

            scene_mgr = SceneManager(im, bus_reg, scene_store=store)
            metric_store = (
                self._metric_store_factory(world_id)
                if self._metric_store_factory
                else None
            )
            state_mgr = StateManager(
                im,
                scene_mgr,
                store,
                store,
                store,
                metric_store=metric_store,
            )
            scene_mgr._state_manager = state_mgr

            # --- NEW: Load static instance declarations ---
            self._load_instance_declarations(world_id, world_dir, im, model_loader)

            state_mgr.restore_world(world_id)
            state_mgr.track_world(world_id)

            bundle = {
                "world_id": world_id,
                "world_yaml": world_yaml,
                "store": store,
                "event_bus_registry": bus_reg,
                "instance_manager": im,
                "scene_manager": scene_mgr,
                "state_manager": state_mgr,
                "metric_store": metric_store,
                "world_state": world_state,
                "lock": world_lock,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
            self._loaded[world_id] = bundle
            return bundle
        except Exception:
            world_lock.release()
            raise

    def _load_instance_declarations(
        self,
        world_id: str,
        world_dir: str,
        im: InstanceManager,
        model_loader,
    ) -> None:
        """Scan and create static instances from agents/**/instances/*.instance.yaml."""
        declarations = InstanceLoader.scan(world_dir)
        for decl in declarations:
            instance_id = decl.get("id")
            model_id = decl.get("modelId")
            if not instance_id or not model_id:
                logger.warning(
                    "Skipping invalid declaration in %s: missing id or modelId",
                    decl.get("_source_file", "unknown"),
                )
                continue

            model = model_loader(model_id)
            if model is None:
                logger.warning(
                    "Model %s not found for instance %s (from %s)",
                    model_id,
                    instance_id,
                    decl.get("_source_file", "unknown"),
                )
                continue

            merged_attrs = _merge_defaults(
                model.get("attributes", {}), decl.get("attributes", {})
            )
            merged_vars = _merge_defaults(
                model.get("variables", {}), decl.get("variables", {})
            )

            # Remove existing instance if declaration conflicts (declaration wins)
            existing = im.get(world_id, instance_id)
            if existing is not None:
                logger.warning(
                    "Declaration %s conflicts with existing instance; replacing",
                    instance_id,
                )
                im.remove(world_id, instance_id)

            state = {"current": None, "enteredAt": None}
            if decl.get("state"):
                state["current"] = decl["state"]

            try:
                im.create(
                    world_id,
                    model_id,
                    instance_id,
                    model=model,
                    state=state,
                    attributes=merged_attrs,
                    variables=merged_vars,
                    memory=decl.get("memory", {}),
                )
            except ValueError as e:
                logger.warning("Failed to create instance %s: %s", instance_id, e)

    # ... unload_world unchanged ...


def _merge_defaults(model_specs: dict, overrides: dict) -> dict:
    """Merge model field specs with declaration overrides.

    For each key in model_specs, use the 'default' value; if the key exists
    in overrides, use the override value instead.
    """
    result = {}
    for key, spec in model_specs.items():
        if isinstance(spec, dict):
            result[key] = overrides.get(key, spec.get("default"))
        else:
            # Legacy: spec is already a scalar value
            result[key] = overrides.get(key, spec)
    # Add any override keys not in model specs
    for key, value in overrides.items():
        if key not in result:
            result[key] = value
    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/runtime/test_world_registry_instance_loading.py -v
```

Expected: 4 passed

- [ ] **Step 5: 运行现有测试确保无回归**

```bash
pytest tests/runtime/ -v
```

Expected: 所有现有测试仍通过

- [ ] **Step 6: Commit**

```bash
git add src/runtime/world_registry.py tests/runtime/test_world_registry_instance_loading.py
git commit -m "feat: integrate static instance declaration loading into WorldRegistry"
```

---

### Task 4: 验证端到端

**Files:**
- Create: `drive_demo_v2.py`（临时验证脚本，不提交）

- [ ] **Step 1: 在 demo-world 中创建真实实例声明**

```bash
mkdir -p worlds/demo-world/agents/logistics/heartbeat/instances
cat > worlds/demo-world/agents/logistics/heartbeat/instances/sensor-01.instance.yaml << 'EOF'
$schema: https://agent-studio.io/schema/v2/instance
id: sensor-01
modelId: heartbeat
state: idle
metadata:
  name: sensor-01
attributes:
  interval: 500
variables:
  count: 0
  temperature: 30
bindings: {}
memory: {}
activeGoals: []
currentPlan: null
extensions: {}
EOF
```

- [ ] **Step 2: 写验证脚本**

```python
# drive_demo_v2.py
import asyncio
from src.runtime.world_registry import WorldRegistry

async def main():
    registry = WorldRegistry()
    bundle = registry.load_world("demo-world")

    im = bundle["instance_manager"]
    bus_reg = bundle["event_bus_registry"]
    event_bus = bus_reg.get_or_create("demo-world")

    # 检查自动加载的实例
    inst = im.get("demo-world", "sensor-01")
    print(f"自动加载实例: {inst.instance_id}")
    print(f"  model_name: {inst.model_name}")
    print(f"  state: {inst.state}")
    print(f"  variables: {inst.variables}")
    print(f"  attributes: {inst.attributes}")

    # 发几个 beat 事件验证 behavior 正常工作
    for i in range(3):
        event_bus.publish("beat", {"seq": i}, source="driver", scope="world")
        await asyncio.sleep(0.3)

    inst = im.get("demo-world", "sensor-01")
    print(f"\n最终 count: {inst.variables.get('count')}")

    registry.unload_world("demo-world")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 运行验证**

```bash
rm -f worlds/demo-world/runtime.db worlds/demo-world/.lock*
.venv/bin/python drive_demo_v2.py
```

Expected: 实例自动加载，behavior 正常工作，count 从 0 增加到 3

- [ ] **Step 4: Commit 验证产物（可选）**

如果 demo-world 的实例声明有价值可以保留：

```bash
git add worlds/demo-world/agents/
git commit -m "chore: add demo-world instance declaration for heartbeat sensor"
```

---

## Spec 覆盖检查

| Spec 要求 | 实现任务 |
|-----------|----------|
| `agents/` 隔离目录结构 | Task 3 WorldRegistry 集成 |
| `modelId` 解析，世界优先 | Task 1 ModelResolver + Task 3 |
| 扫描 `agents/**/instances/*.instance.yaml` | Task 2 InstanceLoader |
| 合并模型默认值 + 声明覆盖值 | Task 3 `_merge_defaults` |
| 在 `restore_world` 之前加载 | Task 3 加载顺序 |
| `model_loader` 注入 InstanceManager | Task 3 `load_world()` |
| ID 冲突：声明覆盖数据库 | Task 3 `_load_instance_declarations` |
| 模型不存在：跳过不阻断 | Task 3 + 测试 `test_load_world_skips_missing_model` |
| 无 `agents/` 目录：向后兼容 | Task 3 + 测试 `test_load_world_no_agents_dir` |
| 全局模型兜底 | Task 1 + Task 3 + 测试 `test_load_world_uses_global_model` |

---

## 无 placeholder 检查

- [x] 无 TBD / TODO
- [x] 所有测试代码完整
- [x] 所有实现代码完整
- [x] 方法签名一致：`model_id` 在 ModelResolver/ModelLoader/InstanceManager 中一致使用
- [x] `model_loader` 闭包签名 `(str) -> dict | None` 与 InstanceManager.__init__ 期望的 `Callable[[str], dict | None]` 匹配
