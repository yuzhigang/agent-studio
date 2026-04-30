# Model Namespace Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce mandatory namespace prefix for all modelIds (`namespace.modelName`), replace rglob with exact-path lookup, and update sync-models discovery logic.

**Architecture:** A new `split_model_id()` parser splits every modelId at the first dot. `_find_model_dir()` becomes exact-path only (`agents/{ns}/{name}/model/`). `sync_models()` iterates namespace directories instead of rglob. All tests updated to use dotted modelIds.

**Tech Stack:** Python, pytest, pathlib

---

## File Structure

| File | Responsibility |
|---|---|
| `src/runtime/model_resolver.py` | Core change: `split_model_id()`, exact-path `_find_model_dir()` |
| `src/runtime/world_registry.py` | `agent_namespace_resolver` now passes dotted modelIds to `resolve()` |
| `src/runtime/instance_loader.py` | `_agent_namespace_for` semantics unchanged (still returns dotted path) |
| `src/cli/main.py` | `sync_models()` discovery and modelId extraction updated |
| `tests/runtime/test_model_resolver.py` | All tests use `core.ladle`, `logistics.sensor.v2` etc. |
| `tests/cli/test_main.py` | sync-models tests use dotted modelIds |

---

## Task 1: ModelResolver Core — `split_model_id()` and Exact-Path Lookup

**Files:**
- Modify: `src/runtime/model_resolver.py`
- Test: `tests/runtime/test_model_resolver.py`

- [ ] **Step 1: Write the failing test**

Replace the entire `tests/runtime/test_model_resolver.py` with tests that use dotted modelIds:

```python
"""Tests for ModelResolver with mandatory namespace."""

import pytest
from pathlib import Path

from src.runtime.model_resolver import ModelResolver
from src.runtime.lib.exceptions import ModelNotFoundError


class TestSplitModelId:
    """Test split_model_id parser."""

    def test_simple(self):
        assert ModelResolver.split_model_id("core.ladle") == ("core", "ladle")

    def test_model_name_with_dot(self):
        assert ModelResolver.split_model_id("logistics.sensor.v2") == ("logistics", "sensor.v2")

    def test_no_dot_raises(self):
        with pytest.raises(ValueError, match="must contain namespace"):
            ModelResolver.split_model_id("ladle")

    def test_empty_namespace_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            ModelResolver.split_model_id(".ladle")

    def test_empty_model_name_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            ModelResolver.split_model_id("core.")

    def test_namespace_with_dot_raises(self):
        with pytest.raises(ValueError, match="namespace must not contain dot"):
            ModelResolver.split_model_id("a.b.ladle")


class TestModelResolver:
    """Test suite for ModelResolver with namespace-aware paths."""

    def test_resolve_in_world_agents(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        model_dir = world_dir / "agents" / "core" / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("core.ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_resolve_no_world_agents_dir(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("core.ladle")

        assert result is None

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("core.nonexistent")

        assert result is None

    def test_resolve_invalid_model_id_raises(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        with pytest.raises(ValueError, match="must contain namespace"):
            resolver.resolve("ladle")

    def test_ensure_copies_from_global(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "core" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("core.ladle")

        assert result.resolve() == (world_dir / "agents" / "core" / "ladle" / "model").resolve()
        assert (world_dir / "agents" / "core" / "ladle" / "model" / "index.yaml").exists()

    def test_ensure_skips_existing_world_model(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_model_dir = world_dir / "agents" / "core" / "ladle" / "model"
        world_model_dir.mkdir(parents=True)
        (world_model_dir / "index.yaml").write_text("name: world-ladle")

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "core" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("core.ladle")

        assert result.resolve() == world_model_dir.resolve()
        assert "world-ladle" in (world_model_dir / "index.yaml").read_text()

    def test_ensure_raises_when_not_found_anywhere(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()
        global_dir = tmp_path / "global"
        global_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        with pytest.raises(ModelNotFoundError):
            resolver.ensure("core.nonexistent")

    def test_ensure_copies_shared_libs(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "core" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")
        shared_libs = global_dir / "shared" / "libs"
        shared_libs.mkdir(parents=True)
        (shared_libs / "util.py").write_text("def hello(): pass")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        resolver.ensure("core.ladle")

        assert (world_dir / "agents" / "shared" / "libs" / "util.py").exists()

    def test_ensure_preserves_namespace_structure(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "logistics" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("logistics.ladle")

        expected = world_dir / "agents" / "logistics" / "ladle" / "model"
        assert result.resolve() == expected.resolve()

    def test_same_name_different_namespace(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        agents = world_dir / "agents"

        (agents / "logistics" / "ladle" / "model").mkdir(parents=True)
        (agents / "steel" / "ladle" / "model").mkdir(parents=True)

        resolver = ModelResolver(str(world_dir), [])
        assert resolver.resolve("logistics.ladle") == agents / "logistics" / "ladle" / "model"
        assert resolver.resolve("steel.ladle") == agents / "steel" / "ladle" / "model"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/runtime/test_model_resolver.py -v
```

Expected: FAIL — `AttributeError: type object 'ModelResolver' has no attribute 'split_model_id'` and all existing tests fail because fixtures use old flat paths (`agents/ladle/model` instead of `agents/core/ladle/model`).

- [ ] **Step 3: Implement `split_model_id()` and update `_find_model_dir()`**

In `src/runtime/model_resolver.py`, after the imports and before the class:

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

Update `_find_model_dir`:

```python
@staticmethod
def _find_model_dir(root: Path, model_id: str) -> Path | None:
    """Exact-path lookup: root/{namespace}/{model_name}/model"""
    namespace, model_name = split_model_id(model_id)
    exact = root / namespace / model_name / "model"
    return exact if exact.is_dir() else None
```

Add `split_model_id` as a static method on the class (for discoverability from tests):

```python
class ModelResolver:
    ...
    split_model_id = staticmethod(split_model_id)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/runtime/test_model_resolver.py -v
```

Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_model_resolver.py src/runtime/model_resolver.py
git commit -m "feat: mandatory namespace prefix for modelId, exact-path lookup"
```

---

## Task 2: sync-models CLI — Namespace-Aware Discovery

**Files:**
- Modify: `src/cli/main.py:148-273`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

In `tests/cli/test_main.py`, add tests for `sync_models` with namespace:

```python
from pathlib import Path
from src.cli.main import sync_models


def test_sync_models_discovers_namespaced_models(tmp_path: Path) -> None:
    global_dir = tmp_path / "agents"
    (global_dir / "core" / "ladle" / "model").mkdir(parents=True)
    (global_dir / "core" / "ladle" / "model" / "index.yaml").write_text("x: 1")
    (global_dir / "logistics" / "sensor" / "model").mkdir(parents=True)
    (global_dir / "logistics" / "sensor" / "model" / "index.yaml").write_text("x: 2")

    world_dir = tmp_path / "world"
    world_dir.mkdir()

    # Monkey-patch global_paths for test
    import src.cli.main as main_module
    original = main_module.sync_models.__globals__.get("global_paths")
    # Use _find_global_root to resolve; instead, just run and capture stdout
    import io
    import sys
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        sync_models(str(world_dir))
    finally:
        sys.stdout = old_stdout

    out = captured.getvalue()
    assert "core.ladle" in out or "ADD" in out
    assert "logistics.sensor" in out or "ADD" in out
```

Wait — `sync_models` hardcodes `global_paths = ["agents"]` and does file IO. Better to refactor `sync_models` first to accept `global_paths` as an argument, or mock the paths.

Simpler: refactor `sync_models` signature to accept optional `global_paths`:

```python
def sync_models(world_dir: str, force: bool = False, global_paths: list[str] | None = None) -> int:
    global_paths = global_paths or ["agents"]
```

Then test:

```python
def test_sync_models_namespaced_discovery(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    (agents / "core" / "ladle" / "model" / "index.yaml").write_text("x: 1")
    world_dir = tmp_path / "world"
    world_dir.mkdir()

    result = sync_models(str(world_dir), global_paths=[str(agents)])
    assert result == 0
    assert (world_dir / "agents" / "core" / "ladle" / "model" / "index.yaml").exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/cli/test_main.py::test_sync_models_namespaced_discovery -v
```

Expected: FAIL — `sync_models` takes no `global_paths` kwarg, and discovery uses `rglob("*/model")` which won't find `agents/core/ladle/model` (it's nested deeper than `*/model`).

- [ ] **Step 3: Implement namespace-aware `sync_models()`**

Replace the model discovery sections in `src/cli/main.py`:

**Before (lines 159-178):**
```python
    global_models: dict[str, Path] = {}
    for gp_str in global_paths:
        gp = Path(gp_str)
        if not gp.exists():
            continue
        for model_dir in gp.rglob("*/model"):
            if not model_dir.is_dir():
                continue
            model_id = model_dir.parent.name
            if model_id not in global_models:
                global_models[model_id] = model_dir
```

**After:**
```python
    def _discover_models(root: Path) -> dict[str, Path]:
        """Discover models under root with two-level namespace structure."""
        models: dict[str, Path] = {}
        if not root.exists():
            return models
        for ns_dir in root.iterdir():
            if not ns_dir.is_dir() or ns_dir.name == "shared":
                continue
            for model_dir in ns_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                if not (model_dir / "model").is_dir():
                    continue
                model_id = f"{ns_dir.name}.{model_dir.name}"
                models[model_id] = model_dir / "model"
        return models

    global_models: dict[str, Path] = {}
    for gp_str in global_paths:
        global_models.update(_discover_models(Path(gp_str)))

    world_models: dict[str, Path] = _discover_models(world_agents)
```

Also update function signature:

```python
def sync_models(world_dir: str, force: bool = False, global_paths: list[str] | None = None) -> int:
    global_paths = global_paths or ["agents"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/cli/test_main.py::test_sync_models_namespaced_discovery -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/cli/test_main.py src/cli/main.py
git commit -m "feat: sync-models discovers namespaced models with two-level structure"
```

---

## Task 3: InstanceLoader and WorldRegistry — Adapter Updates

**Files:**
- Modify: `src/runtime/world_registry.py:106-110`
- Modify: `src/runtime/instance_loader.py` (no change needed — `_agent_namespace_for` still returns dotted path)
- Test: Existing integration tests should still pass after updating fixtures

- [ ] **Step 1: Verify no code changes needed for InstanceLoader**

`InstanceLoader._agent_namespace_for` calls `agent_namespace_for_path(file_path, agents_dir, "instances")`. With the new two-level structure:

- File path: `agents/logistics/ladle/instances/foo.instance.yaml`
- `rel.parts = ("logistics", "ladle", "instances")`
- `agent_parts = ("logistics", "ladle")`
- Returns `"logistics.ladle"`

This is **correct** — the `_agent_namespace` now equals the full modelId. No code changes needed.

- [ ] **Step 2: Verify WorldRegistry agent_namespace_resolver**

```python
def agent_namespace_resolver(model_id: str) -> str | None:
    model_dir = resolver.resolve(model_id)
    if model_dir is None:
        return None
    return agent_namespace_for_path(model_dir, world_agents_dir, "model")
```

With modelId = `"logistics.ladle"`:
- `resolve("logistics.ladle")` returns `agents/logistics/ladle/model`
- `agent_namespace_for_path(...)` returns `"logistics.ladle"`

This is correct. The `_agent_namespace` field on Instance will now hold `"logistics.ladle"`, which is exactly the modelId. This is fine because `LibProxy` uses it as `default_namespace`.

**No code changes needed in WorldRegistry or InstanceLoader.**

- [ ] **Step 3: Update any integration test fixtures**

Search for tests that create old flat model directories (`agents/ladle/model`) and update them:

```bash
rgrep -n "agents/.*/model" tests/ --include="*.py"
```

Any test that creates `agents/ladle/model` (without namespace) must be updated to `agents/core/ladle/model` and use modelId `core.ladle`.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All pass (or identify remaining fixtures to fix)

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor: update test fixtures for namespaced modelIds"
```

---

## Task 4: Run Full Regression Test

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: All existing + new tests pass

- [ ] **Step 2: Commit any fixes**

If failures, fix and commit.

---

## Test Summary

| Test | File | What it covers |
|---|---|---|
| `test_simple` | `test_model_resolver.py` | `split_model_id("core.ladle")` → `("core", "ladle")` |
| `test_model_name_with_dot` | `test_model_resolver.py` | `split_model_id("logistics.sensor.v2")` |
| `test_no_dot_raises` | `test_model_resolver.py` | Invalid modelId raises ValueError |
| `test_empty_namespace_raises` | `test_model_resolver.py` | `.ladle` raises ValueError |
| `test_empty_model_name_raises` | `test_model_resolver.py` | `core.` raises ValueError |
| `test_namespace_with_dot_raises` | `test_model_resolver.py` | `a.b.ladle` raises ValueError |
| `test_resolve_in_world_agents` | `test_model_resolver.py` | Exact-path resolve works |
| `test_resolve_invalid_model_id_raises` | `test_model_resolver.py` | `resolve("ladle")` raises ValueError |
| `test_ensure_copies_from_global` | `test_model_resolver.py` | Ensure copies with namespace |
| `test_same_name_different_namespace` | `test_model_resolver.py` | `logistics.ladle` vs `steel.ladle` |
| `test_sync_models_namespaced_discovery` | `test_main.py` | sync-models finds `core.ladle` |
