# Scene Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate scene stop from permanent removal while preserving shared world instances and supporting definition-driven restart and deletion.

**Architecture:** `SceneManager._scenes` remains the running-scene registry, while SQLite and YAML hold definitions. Stop removes scene-scope runtime instances only; worker commands load persisted definitions for start/list and invoke a preflighted remove operation that deletes YAML before SQLite.

**Tech Stack:** Python 3.11+, SQLite, PyYAML, aiohttp, pytest

---

## File Map

- Modify `src/runtime/scene_manager.py`: retain complete definitions, stop only runtime instances, and remove persisted definitions.
- Modify `src/worker/commands/scene.py`: definition-driven start, definition-based list, and remove command.
- Modify `src/worker/commands/__init__.py`: register `scene.remove`.
- Modify `src/supervisor/handlers/scenes.py`: proxy remove.
- Modify `src/supervisor/handlers/__init__.py`: export remove handler.
- Modify `src/supervisor/server.py`: add DELETE scene route.
- Modify focused scene, worker command, registry, and supervisor tests.

### Task 1: Stop Runtime Instances Without Deleting Definitions

**Files:**
- Modify: `src/runtime/scene_manager.py`
- Test: `tests/runtime/test_scene_manager.py`
- Test: `tests/runtime/test_world_instance_scene_integration.py`
- Test: `tests/runtime/test_world_registry.py`

- [ ] **Step 1: Write failing stop and definition-integrity tests**

Change the existing stop assertions and add shared-local coverage:

```python
def test_stop_scene_preserves_definition_in_store():
    class RecordingStore:
        def __init__(self):
            self.saved = {}
            self.deleted = []

        def save_scene(self, world_id, scene_id, scene_data):
            self.saved[(world_id, scene_id)] = scene_data

        def delete_scene(self, world_id, scene_id):
            self.deleted.append((world_id, scene_id))

    store = RecordingStore()
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create("world-01", "ladle", "ladle-001")
    ctrl = SceneManager(im, bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated", references=["ladle-001"])
    ctrl.stop("world-01", "drill")
    assert ("world-01", "drill") in store.saved
    assert store.deleted == []


def test_stop_shared_scene_preserves_world_references_and_removes_local_instances():
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    im.create("world-01", "ladle", "ladle-001")
    ctrl = SceneManager(im, bus_reg)
    ctrl.start(
        "world-01",
        "monitor",
        mode="shared",
        references=["ladle-001"],
        local_instances={"temp-01": {"modelName": "inspector"}},
    )
    ctrl.stop("world-01", "monitor")
    assert im.get("world-01", "ladle-001", "world") is not None
    assert im.list_by_scope("world-01", "scene:monitor") == []
```

Update the local-instance namespace test to assert that the running scene and
SQLite definition retain the complete local specification:

```python
assert scene["local_instances"]["ladle-local-01"] == {
    "modelName": "logistics.ladle"
}
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_scene_manager.py tests/runtime/test_world_instance_scene_integration.py tests/runtime/test_world_registry.py -q
```

Expected: stop deletes the store definition and local specifications are
replaced by runtime IDs.

- [ ] **Step 3: Preserve complete definitions and change stop**

In `SceneManager.start()`, deep-copy the supplied local definitions into the
scene record:

```python
scene = {
    "world_id": world_id,
    "scene_id": scene_id,
    "mode": mode,
    "references": resolved_refs,
    "local_instances": copy.deepcopy(local_instances),
}
```

Validate each local specification before creating instances:

```python
if not isinstance(local_spec, dict) or not local_spec.get("modelName"):
    raise ValueError(f"Invalid local instance definition for {local_id}")
```

In `stop()`, first read the running scene, remove every instance whose scope is
`scene:<scene_id>`, then pop the scene from `_scenes`. Remove the call to
`delete_scene()`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_scene_manager.py tests/runtime/test_world_instance_scene_integration.py tests/runtime/test_world_registry.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit stop semantics**

```powershell
git add src/runtime/scene_manager.py tests/runtime/test_scene_manager.py tests/runtime/test_world_instance_scene_integration.py tests/runtime/test_world_registry.py
git commit -m "fix: preserve scene definitions on stop"
```

### Task 2: Definition-Driven Start and Scene Listing

**Files:**
- Modify: `src/worker/commands/scene.py`
- Test: `tests/worker/test_commands.py`

- [ ] **Step 1: Write failing worker command tests**

Add tests proving stopped definitions restart with persisted configuration and
missing definitions do not create isolated scenes:

```python
@pytest.mark.anyio
async def test_scene_start_uses_persisted_definition(manager):
    from unittest.mock import MagicMock

    scene_manager = MagicMock()
    scene_manager.get.return_value = None
    store = MagicMock()
    store.load_scene.return_value = {
        "mode": "shared",
        "refs": ["agent-1"],
        "local_instances": {"local-1": {"modelName": "inspector"}},
    }
    bundle = {"scene_manager": scene_manager, "store": store}
    result = await scene_start(manager, bundle, {"world_id": "w1", "scene_id": "s1"})
    assert result == {"status": "started"}
    scene_manager.start.assert_called_once_with(
        "w1",
        "s1",
        mode="shared",
        references=["agent-1"],
        local_instances={"local-1": {"modelName": "inspector"}},
    )


@pytest.mark.anyio
async def test_scene_start_missing_definition_raises_scene_not_found(manager):
    from unittest.mock import MagicMock

    scene_manager = MagicMock()
    scene_manager.get.return_value = None
    store = MagicMock()
    store.load_scene.return_value = None
    bundle = {"scene_manager": scene_manager, "store": store}
    with pytest.raises(JsonRpcError) as exc:
        await scene_start(manager, bundle, {"world_id": "w1", "scene_id": "missing"})
    assert exc.value.code == -32002
```

Update scene listing coverage to provide SQLite definitions and assert:

```python
assert result["scenes"] == [
    {"scene_id": "s1", "mode": "shared", "status": "running", "instance_count": 1},
    {"scene_id": "s2", "mode": "isolated", "status": "stopped", "instance_count": 0},
]
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/worker/test_commands.py -q
```

Expected: `scene.start` defaults to isolated mode and listing omits stopped
definitions and status.

- [ ] **Step 3: Implement definition-driven commands**

Change `scene_start()` to load `bundle["store"].load_scene()` and call
`SceneManager.start()` with:

```python
mode=definition["mode"],
references=definition.get("refs", []),
local_instances=definition.get("local_instances", {}),
```

Raise `JsonRpcError(-32002, "scene not found")` when the definition is absent.

Change `world_scenes_list()` to iterate over
`bundle["store"].list_scenes(world_id)`, use `sm.get()` to determine status,
and count only instances whose scope equals `scene:<scene_id>`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/worker/test_commands.py tests/runtime/test_scene_manager.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit command semantics**

```powershell
git add src/worker/commands/scene.py tests/worker/test_commands.py
git commit -m "feat: start scenes from persisted definitions"
```

### Task 3: Permanently Remove Scene Definitions

**Files:**
- Modify: `src/runtime/scene_manager.py`
- Modify: `src/worker/commands/scene.py`
- Modify: `src/worker/commands/__init__.py`
- Test: `tests/runtime/test_scene_manager.py`
- Test: `tests/worker/test_commands.py`

- [ ] **Step 1: Write failing SceneManager remove tests**

Add tests using real temporary YAML files and a fake scene store:

```python
class RecordingSceneStore:
    def __init__(self):
        self.saved = {}
        self.deleted = []

    def save_scene(self, world_id, scene_id, scene_data):
        self.saved[(world_id, scene_id)] = scene_data

    def load_scene(self, world_id, scene_id):
        return self.saved.get((world_id, scene_id))

    def delete_scene(self, world_id, scene_id):
        self.deleted.append((world_id, scene_id))
        return self.saved.pop((world_id, scene_id), None) is not None


def test_remove_running_yaml_scene_stops_and_deletes_both_definitions(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    yaml_path = scenes_dir / "drill.yaml"
    yaml_path.write_text("scene_id: drill\nmode: isolated\n", encoding="utf-8")
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    im = InstanceManager(bus_reg)
    ctrl = SceneManager(im, bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated")
    assert ctrl.remove("world-01", "drill", tmp_path / "scenes") is True
    assert ctrl.get("world-01", "drill") is None
    assert not yaml_path.exists()
    assert ("world-01", "drill") in store.deleted


def test_remove_runtime_only_scene_deletes_store_definition(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "runtime-scene", mode="shared")
    assert ctrl.remove("world-01", "runtime-scene", tmp_path / "scenes") is True
    assert ("world-01", "runtime-scene") in store.deleted


def test_remove_duplicate_yaml_scene_fails_before_changes(tmp_path):
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    (scenes_dir / "first.yaml").write_text("scene_id: drill\n", encoding="utf-8")
    (scenes_dir / "second.yaml").write_text("scene_id: drill\n", encoding="utf-8")
    store = RecordingSceneStore()
    bus_reg = EventBusRegistry()
    ctrl = SceneManager(InstanceManager(bus_reg), bus_reg, scene_store=store)
    ctrl.start("world-01", "drill", mode="isolated")
    with pytest.raises(ValueError, match="Multiple YAML definitions"):
        ctrl.remove("world-01", "drill", tmp_path / "scenes")
    assert ctrl.get("world-01", "drill") is not None
    assert store.deleted == []
```

Add an unreadable or malformed YAML test and an absent-scene test.

- [ ] **Step 2: Run SceneManager remove tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_scene_manager.py -q
```

Expected: `SceneManager` has no `remove()` method.

- [ ] **Step 3: Implement preflighted SceneManager.remove**

Add a helper that recursively scans `Path(scenes_dir).rglob("*.yaml")`, parses
each file with `yaml.safe_load()`, and returns exact `scene_id` matches.

Implement:

```python
def remove(self, world_id: str, scene_id: str, scenes_dir: str | Path) -> bool:
    definition = self._scene_store.load_scene(world_id, scene_id) if self._scene_store else None
    yaml_matches = self._find_yaml_definitions(scenes_dir, scene_id)
    running = self.get(world_id, scene_id) is not None
    if len(yaml_matches) > 1:
        raise ValueError(f"Multiple YAML definitions found for scene {scene_id}")
    if not running and definition is None and not yaml_matches:
        return False
    if running:
        self.stop(world_id, scene_id)
    if yaml_matches:
        yaml_matches[0].unlink()
    if self._scene_store is not None:
        self._scene_store.delete_scene(world_id, scene_id)
    return True
```

Let YAML parsing, unlink, and store errors propagate.

- [ ] **Step 4: Write failing worker remove command tests**

Add tests proving `scene_remove()` derives the scenes directory from
`bundle["store"]._world_dir`, returns `removed`, and maps `False` to JSON-RPC
code `-32002`. Assert `get_handler("scene.remove")` returns the command.

- [ ] **Step 5: Run worker remove tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/worker/test_commands.py -q
```

Expected: `scene_remove` and registry entry are absent.

- [ ] **Step 6: Implement and register worker remove command**

Add:

```python
async def scene_remove(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    scene_id = params.get("scene_id")
    if scene_id is None:
        raise JsonRpcError(-32602, "scene_id required")
    scenes_dir = Path(bundle["store"]._world_dir) / "scenes"
    ok = await asyncio.to_thread(
        bundle["scene_manager"].remove, world_id, scene_id, scenes_dir
    )
    if not ok:
        raise JsonRpcError(-32002, "scene not found")
    return {"status": "removed"}
```

Register `"scene.remove": scene_remove` in the worker command registry.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_scene_manager.py tests/worker/test_commands.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit remove behavior**

```powershell
git add src/runtime/scene_manager.py src/worker/commands/scene.py src/worker/commands/__init__.py tests/runtime/test_scene_manager.py tests/worker/test_commands.py
git commit -m "feat: remove persisted scene definitions"
```

### Task 4: Supervisor Remove API

**Files:**
- Modify: `src/supervisor/handlers/scenes.py`
- Modify: `src/supervisor/handlers/__init__.py`
- Modify: `src/supervisor/server.py`
- Test: `tests/supervisor/test_api.py`
- Test: `tests/supervisor/test_server.py`

- [ ] **Step 1: Write failing supervisor handler and route tests**

Add a handler test that calls `handle_scene_remove()` with a fake request and
asserts the controller receives:

```python
("w1", "scene.remove", {"world_id": "w1", "scene_id": "s1"})
```

Assert a successful worker response returns HTTP 200 and
`{"status": "removed"}`. Add a scene-not-found mapping test.

Add or extend a server route test to assert:

```python
("DELETE", "/api/worlds/{world_id}/scenes/{scene_id}")
```

is registered.

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
uv run --frozen pytest tests/supervisor/test_api.py tests/supervisor/test_server.py -q
```

Expected: remove handler and DELETE route are absent.

- [ ] **Step 3: Implement supervisor remove API**

Add `handle_scene_remove()` using the same WorkerRpcError and TimeoutError
handling pattern as `handle_scene_stop()`. Export it from
`src/supervisor/handlers/__init__.py` and register:

```python
app.router.add_delete(
    "/api/worlds/{world_id}/scenes/{scene_id}",
    handlers.handle_scene_remove,
)
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --frozen pytest tests/supervisor/test_api.py tests/supervisor/test_server.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit supervisor API**

```powershell
git add src/supervisor/handlers/scenes.py src/supervisor/handlers/__init__.py src/supervisor/server.py tests/supervisor/test_api.py tests/supervisor/test_server.py
git commit -m "feat: expose scene removal API"
```

### Task 5: Scene Lifecycle Integration Verification

**Files:**
- Modify only files required to correct regressions introduced by Tasks 1-4.

- [ ] **Step 1: Run all scene-lifecycle focused tests**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_scene_manager.py tests/runtime/test_world_instance_scene_integration.py tests/runtime/test_world_registry.py tests/worker/test_commands.py tests/worker/test_manager.py tests/supervisor/test_api.py tests/supervisor/test_server.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the phase-1 runtime regression set**

Run:

```powershell
uv run --frozen pytest tests/runtime/test_event_bus.py tests/runtime/test_state_manager.py tests/runtime/test_world_registry_instance_loading.py tests/runtime/stores/test_sqlite_store.py tests/runtime/test_instance_manager.py tests/runtime/test_trigger_registry.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run the full frozen suite**

Run:

```powershell
uv run --frozen pytest -q
```

Expected: no new failures compared with the documented baseline. Record the
existing missing `aio_pika`, missing `aiohttp_client`, Supervisor, and JSON-RPC
failures without changing dependency scope.

- [ ] **Step 4: Check worktree boundaries**

Run:

```powershell
git diff --check
git status --short
```

Expected: no phase-related unstaged changes remain; unrelated pre-existing
worktree changes remain untouched.
