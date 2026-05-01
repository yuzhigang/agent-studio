# Worker Command Handler Refactor Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic `handle_command` in `WorkerManager` into isolated per-domain command modules under `src/worker/commands/`.

**Architecture:** Each command becomes a standalone async function in a domain file (`world.py`, `instance.py`, `scene.py`, `model.py`, `message_hub.py`). `WorkerManager.handle_command` shrinks to a 10-line dispatcher that looks up the handler in a registry imported from `src.worker.commands`.

**Tech Stack:** Python, pytest

---

## File Structure

| File | Responsibility |
|---|---|
| `src/worker/commands/__init__.py` | Registry: maps method name -> handler function |
| `src/worker/commands/world.py` | `world.stop`, `world.remove`, `world.checkpoint`, `world.getStatus`, `world.start`, `world.reload` |
| `src/worker/commands/instance.py` | `world.instances.list`, `world.instances.get` |
| `src/worker/commands/scene.py` | `scene.start`, `scene.stop`, `world.scenes.list` |
| `src/worker/commands/model.py` | `world.models.list`, `world.models.get` |
| `src/worker/commands/message_hub.py` | `messageHub.publish`, `messageHub.publishBatch` |
| `src/worker/manager.py` | Keep `WorkerManager` class; replace `handle_command` body with dispatcher |
| `tests/worker/test_commands.py` | Tests for extracted command handlers |

---

## Task 1: Scaffold `src/worker/commands/` Package

**Files:**
- Create: `src/worker/commands/__init__.py`
- Create: `src/worker/commands/world.py`
- Create: `src/worker/commands/instance.py`
- Create: `src/worker/commands/scene.py`
- Create: `src/worker/commands/model.py`
- Create: `src/worker/commands/message_hub.py`

- [ ] **Step 1: Create package init with registry**

`src/worker/commands/__init__.py`:

```python
from src.worker.commands.world import (
    world_checkpoint,
    world_get_status,
    world_reload,
    world_remove,
    world_start,
    world_stop,
)
from src.worker.commands.instance import world_instances_get, world_instances_list
from src.worker.commands.scene import scene_start, scene_stop, world_scenes_list
from src.worker.commands.model import world_models_get, world_models_list
from src.worker.commands.message_hub import message_hub_publish, message_hub_publish_batch

_REGISTRY = {
    "world.stop": world_stop,
    "world.remove": world_remove,
    "world.checkpoint": world_checkpoint,
    "world.getStatus": world_get_status,
    "world.instances.list": world_instances_list,
    "world.instances.get": world_instances_get,
    "world.start": world_start,
    "world.reload": world_reload,
    "scene.start": scene_start,
    "scene.stop": scene_stop,
    "world.scenes.list": world_scenes_list,
    "world.models.list": world_models_list,
    "world.models.get": world_models_get,
    "messageHub.publish": message_hub_publish,
    "messageHub.publishBatch": message_hub_publish_batch,
}


def get_handler(method: str):
    return _REGISTRY.get(method)
```

- [ ] **Step 2: Create stub command files**

Each file starts with a single placeholder function so imports work:

`src/worker/commands/world.py`:
```python
async def world_stop(manager, bundle, params):
    raise NotImplementedError
```

(Same pattern for all other files.)

- [ ] **Step 3: Commit**

```bash
git add src/worker/commands/
git commit -m "chore: scaffold worker commands package"
```

---

## Task 2: Extract World Commands

**Files:**
- Modify: `src/worker/manager.py` (remove world command blocks)
- Modify: `src/worker/commands/world.py`

- [ ] **Step 1: Move world.stop logic**

`src/worker/commands/world.py`:

```python
import asyncio
import os

from src.runtime.world_registry import WorldRegistry
from src.worker.server.jsonrpc_ws import JsonRpcError


async def world_stop(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    force = params.get("force_stop_on_shutdown")
    await manager._graceful_shutdown(bundle, force_stop_on_shutdown=force, permanent=False)
    return {"status": "stopped"}
```

- [ ] **Step 2: Move world.remove logic**

```python
async def world_remove(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    force = params.get("force_stop_on_shutdown")
    await manager._graceful_shutdown(bundle, force_stop_on_shutdown=force, permanent=True)
    manager.worlds.pop(world_id, None)
    return {"status": "removed"}
```

- [ ] **Step 3: Move world.checkpoint logic**

```python
async def world_checkpoint(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    await asyncio.to_thread(bundle["state_manager"].checkpoint_world, world_id)
    return {"status": "checkpointed"}
```

- [ ] **Step 4: Move world.getStatus logic**

```python
async def world_get_status(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    return {
        "world_id": world_id,
        "loaded": True,
        "status": bundle.get("runtime_status", "running"),
        "scenes": [s["scene_id"] for s in bundle["scene_manager"].list_by_world(world_id)],
    }
```

- [ ] **Step 5: Move world.start logic**

```python
async def world_start(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is not None:
        if bundle.get("runtime_status", "running") == "running":
            return {"status": "already_running"}
        manager._bind_world_bundle(world_id, bundle)
        manager._start_shared_scenes_for_bundle(bundle)
        state_mgr = bundle.get("state_manager")
        if state_mgr is not None and state_mgr._task is None:
            await state_mgr.start_async()
        bundle["runtime_status"] = "running"
        return {"status": "started"}
    world_dir = params.get("world_dir")
    if world_dir is None:
        raise JsonRpcError(-32602, "world_dir required for world.start")
    base_dir = os.path.dirname(os.path.abspath(world_dir))
    registry = WorldRegistry(base_dir=base_dir)
    new_bundle = await asyncio.to_thread(registry.load_world, world_id)
    manager.worlds[world_id] = new_bundle
    manager._bind_world_bundle(world_id, new_bundle)
    manager._start_shared_scenes_for_bundle(new_bundle)
    state_mgr = new_bundle.get("state_manager")
    if state_mgr is not None and state_mgr._task is None:
        await state_mgr.start_async()
    new_bundle["runtime_status"] = "running"
    return {"status": "started"}
```

- [ ] **Step 6: Move world.reload logic**

```python
async def world_reload(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    raise JsonRpcError(-32601, "world.reload not yet implemented")
```

- [ ] **Step 7: Remove moved blocks from manager.py**

In `src/worker/manager.py`, delete these `if method == "world.xxx"` blocks from `handle_command`:
- `world.stop` (lines 184-193)
- `world.remove` (lines 195-205)
- `world.checkpoint` (lines 207-211)
- `world.getStatus` (lines 213-221)
- `world.instances.list` (lines 223-240)
- `world.start` (lines 242-266)
- `world.reload` (lines 268-271)

Leave only `scene.*` and `messageHub.*` blocks for now.

- [ ] **Step 8: Run existing tests**

Run: `pytest tests/worker/ -v`
Expected: All PASS (behavior unchanged, only code moved)

- [ ] **Step 9: Commit**

```bash
git add src/worker/commands/world.py src/worker/manager.py
git commit -m "refactor: extract world commands to src/worker/commands/world.py"
```

---

## Task 3: Extract Instance Commands

**Files:**
- Modify: `src/worker/manager.py`
- Modify: `src/worker/commands/instance.py`

- [ ] **Step 1: Move world.instances.list logic**

`src/worker/commands/instance.py`:

```python
from src.worker.server.jsonrpc_ws import JsonRpcError


async def world_instances_list(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    instances = bundle["instance_manager"].list_by_world(world_id)
    return {
        "instances": [
            {
                "id": inst.instance_id,
                "model": inst.model_name,
                "scope": inst.scope,
                "state": inst.state.get("current"),
                "lifecycle_state": inst.lifecycle_state,
                "variables": inst.variables,
                "attributes": inst.attributes,
            }
            for inst in instances
        ]
    }
```

- [ ] **Step 2: Implement world.instances.get (new command)**

```python
async def world_instances_get(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    instance_id = params.get("instance_id")
    if instance_id is None:
        raise JsonRpcError(-32602, "instance_id required")
    inst = bundle["instance_manager"].get(world_id, instance_id)
    if inst is None:
        raise JsonRpcError(-32004, f"Instance {instance_id} not found")
    return {
        "instance_id": inst.instance_id,
        "model_name": inst.model_name,
        "scope": inst.scope,
        "state": inst.state,
        "lifecycle_state": inst.lifecycle_state,
        "variables": inst.variables,
        "attributes": inst.attributes,
        "bindings": inst.bindings,
        "links": inst.links,
        "memory": inst.memory,
        "audit": inst.audit,
    }
```

- [ ] **Step 3: Remove instance blocks from manager.py**

Delete `world.instances.list` block from `handle_command`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/worker/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/commands/instance.py src/worker/manager.py
git commit -m "refactor: extract instance commands; add world.instances.get"
```

---

## Task 4: Extract Scene Commands

**Files:**
- Modify: `src/worker/manager.py`
- Modify: `src/worker/commands/scene.py`

- [ ] **Step 1: Move scene.start and scene.stop logic**

`src/worker/commands/scene.py`:

```python
import asyncio

from src.worker.server.jsonrpc_ws import JsonRpcError


async def scene_start(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    scene_id = params.get("scene_id")
    if scene_id is None:
        raise JsonRpcError(-32602, "scene_id required")
    existing = bundle["scene_manager"].get(world_id, scene_id)
    if existing is not None:
        return {"status": "already_running"}
    await asyncio.to_thread(bundle["scene_manager"].start, world_id, scene_id, mode="isolated")
    return {"status": "started"}


async def scene_stop(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    scene_id = params.get("scene_id")
    if scene_id is None:
        raise JsonRpcError(-32602, "scene_id required")
    ok = await asyncio.to_thread(bundle["scene_manager"].stop, world_id, scene_id)
    if not ok:
        raise JsonRpcError(-32002, "scene not found")
    return {"status": "stopped"}
```

- [ ] **Step 2: Implement world.scenes.list (new command)**

```python
async def world_scenes_list(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    sm = bundle["scene_manager"]
    im = bundle["instance_manager"]
    scenes = sm.list_by_world(world_id)
    instances = im.list_by_world(world_id)
    result = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        scope = f"scene:{scene_id}"
        count = sum(1 for inst in instances if inst.scope == scope)
        result.append({
            "scene_id": scene_id,
            "mode": scene.get("mode", "shared"),
            "instance_count": count,
        })
    return {"scenes": result}
```

- [ ] **Step 3: Remove scene blocks from manager.py**

Delete `scene.start` and `scene.stop` blocks from `handle_command`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/worker/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/commands/scene.py src/worker/manager.py
git commit -m "refactor: extract scene commands; add world.scenes.list"
```

---

## Task 5: Extract Model Commands

**Files:**
- Modify: `src/worker/commands/model.py`

- [ ] **Step 1: Implement world.models.list and world.models.get**

`src/worker/commands/model.py`:

```python
from pathlib import Path

from src.runtime.model_loader import ModelLoader
from src.worker.server.jsonrpc_ws import JsonRpcError


async def world_models_list(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    world_dir = bundle.get("world_dir")
    if world_dir is None:
        raise JsonRpcError(-32004, "world_dir not available")
    agents_dir = Path(world_dir) / "agents"
    models = []
    if agents_dir.exists():
        for model_dir in sorted(agents_dir.iterdir()):
            if model_dir.is_dir() and (model_dir / "model" / "index.yaml").exists():
                try:
                    data = ModelLoader.load(str(model_dir))
                    models.append({
                        "model_id": model_dir.name,
                        "metadata": data.get("metadata", {}),
                    })
                except Exception:
                    pass
    return {"models": models}


async def world_models_get(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    model_id = params.get("model_id")
    if model_id is None:
        raise JsonRpcError(-32602, "model_id required")
    world_dir = bundle.get("world_dir")
    if world_dir is None:
        raise JsonRpcError(-32004, "world_dir not available")
    model_path = Path(world_dir) / "agents" / model_id
    if not (model_path / "model" / "index.yaml").exists():
        raise JsonRpcError(-32004, f"Model {model_id} not found")
    data = ModelLoader.load(str(model_path))
    data["model_id"] = model_id
    return data
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/worker/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/worker/commands/model.py
git commit -m "feat: add world.models.list and world.models.get commands"
```

---

## Task 6: Extract Message Hub Commands

**Files:**
- Modify: `src/worker/manager.py`
- Modify: `src/worker/commands/message_hub.py`

- [ ] **Step 1: Move messageHub.publish and messageHub.publishBatch logic**

`src/worker/commands/message_hub.py`:

```python
from src.worker.server.jsonrpc_ws import JsonRpcError


async def message_hub_publish(manager, bundle, params):
    hub = manager._message_hub
    if hub is None:
        raise JsonRpcError(-32102, "message hub not initialized")
    hub.on_inbound(manager._message_envelope_from_params(params))
    return {"acked": True}


async def message_hub_publish_batch(manager, bundle, params):
    hub = manager._message_hub
    if hub is None:
        raise JsonRpcError(-32102, "message hub not initialized")
    records = params.get("records", [])
    for record in records:
        hub.on_inbound(
            manager._message_envelope_from_params(
                record,
                default_target_world=params.get("target_world"),
            )
        )
    return {
        "acked_ids": [
            record.get("message_id") or record.get("id")
            for record in records
        ]
    }
```

- [ ] **Step 2: Remove messageHub blocks from manager.py**

Delete `messageHub.publish` and `messageHub.publishBatch` blocks from `handle_command`.

- [ ] **Step 3: Replace handle_command with dispatcher**

Replace the entire body of `handle_command` in `src/worker/manager.py`:

```python
    async def handle_command(self, method: str, params: dict) -> dict:
        """Handle a command from Supervisor asynchronously."""
        from src.worker.commands import get_handler

        handler = get_handler(method)
        if handler is None:
            raise JsonRpcError(-32601, f"Unknown method: {method}")

        world_id = params.get("world_id")
        bundle = self.worlds.get(world_id) if world_id else None
        return await handler(self, bundle, params)
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/worker/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/commands/message_hub.py src/worker/manager.py
git commit -m "refactor: extract message hub commands; replace handle_command with dispatcher"
```

---

## Task 7: Add Tests for Extracted Commands

**Files:**
- Create: `tests/worker/test_commands.py`

- [ ] **Step 1: Write tests for extracted handlers**

```python
import pytest
from src.worker.commands.world import world_stop, world_get_status
from src.worker.commands.instance import world_instances_list, world_instances_get
from src.worker.commands.scene import scene_start, scene_stop, world_scenes_list
from src.worker.commands.model import world_models_list, world_models_get
from src.worker.server.jsonrpc_ws import JsonRpcError


@pytest.fixture
def mock_bundle():
    return {"world_id": "w1"}


@pytest.fixture
def manager(mock_bundle):
    from src.worker.manager import WorkerManager
    m = WorkerManager()
    m.worlds = {"w1": mock_bundle}
    return m


@pytest.mark.anyio
async def test_world_stop_missing_bundle(manager):
    with pytest.raises(JsonRpcError) as exc:
        await world_stop(manager, None, {"world_id": "missing"})
    assert exc.value.code == -32004


@pytest.mark.anyio
async def test_world_get_status_ok(manager, mock_bundle):
    mock_bundle["scene_manager"] = type("SM", (), {
        "list_by_world": lambda self, wid: [{"scene_id": "s1"}]
    })()
    result = await world_get_status(manager, mock_bundle, {"world_id": "w1"})
    assert result["status"] == "running"
    assert result["scenes"] == ["s1"]


@pytest.mark.anyio
async def test_world_instances_list(manager, mock_bundle):
    mock_bundle["instance_manager"] = type("IM", (), {
        "list_by_world": lambda self, wid: [
            type("Inst", (), {
                "instance_id": "i1",
                "model_name": "robot",
                "scope": "world",
                "state": {"current": "idle"},
                "lifecycle_state": "active",
                "variables": {},
                "attributes": {},
            })()
        ]
    })()
    result = await world_instances_list(manager, mock_bundle, {"world_id": "w1"})
    assert len(result["instances"]) == 1
    assert result["instances"][0]["id"] == "i1"


@pytest.mark.anyio
async def test_world_instances_get_found(manager, mock_bundle):
    mock_inst = type("Inst", (), {
        "instance_id": "i1",
        "model_name": "robot",
        "scope": "world",
        "state": {"current": "idle"},
        "lifecycle_state": "active",
        "variables": {},
        "attributes": {},
        "bindings": {},
        "links": {},
        "memory": {},
        "audit": {},
    })()
    mock_bundle["instance_manager"] = type("IM", (), {
        "get": lambda self, wid, iid: mock_inst if iid == "i1" else None
    })()
    result = await world_instances_get(manager, mock_bundle, {"world_id": "w1", "instance_id": "i1"})
    assert result["instance_id"] == "i1"


@pytest.mark.anyio
async def test_scene_start_already_running(manager, mock_bundle):
    mock_bundle["scene_manager"] = type("SM", (), {
        "get": lambda self, wid, sid: {"scene_id": sid} if sid == "s1" else None
    })()
    result = await scene_start(manager, mock_bundle, {"world_id": "w1", "scene_id": "s1"})
    assert result["status"] == "already_running"


@pytest.mark.anyio
async def test_world_scenes_list(manager, mock_bundle):
    mock_bundle["scene_manager"] = type("SM", (), {
        "list_by_world": lambda self, wid: [
            {"scene_id": "s1", "mode": "shared"},
            {"scene_id": "s2", "mode": "isolated"},
        ]
    })()
    mock_bundle["instance_manager"] = type("IM", (), {
        "list_by_world": lambda self, wid: [
            type("Inst", (), {"scope": "world"})(),
            type("Inst", (), {"scope": "scene:s1"})(),
            type("Inst", (), {"scope": "scene:s1"})(),
            type("Inst", (), {"scope": "scene:s2"})(),
        ]
    })()
    result = await world_scenes_list(manager, mock_bundle, {"world_id": "w1"})
    assert len(result["scenes"]) == 2
    assert result["scenes"][0]["instance_count"] == 2
    assert result["scenes"][1]["instance_count"] == 1


@pytest.mark.anyio
async def test_world_models_list(manager, tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "robot" / "model").mkdir(parents=True)
    (agents_dir / "robot" / "model" / "index.yaml").write_text("metadata:\n  name: Robot\n")

    mock_bundle = {"world_id": "w1", "world_dir": str(tmp_path)}
    result = await world_models_list(manager, mock_bundle, {"world_id": "w1"})
    assert len(result["models"]) == 1
    assert result["models"][0]["model_id"] == "robot"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/worker/test_commands.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/worker/test_commands.py
git commit -m "test: add unit tests for extracted command handlers"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run full worker test suite**

Run: `pytest tests/worker/ -v`
Expected: All PASS

- [ ] **Step 2: Verify manager.py handle_command length**

Confirm `handle_command` in `src/worker/manager.py` is ~15 lines (dispatcher only).

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: complete worker command handler extraction"
```

---

## Blocking Dependency

This refactor plan **must be completed before** executing `2026-04-30-frontend-api.md`. The frontend API plan adds new commands (`world.instances.get`, `world.scenes.list`, `world.models.list`, `world.models.get`) which are already included above as new commands in the extracted modules.
