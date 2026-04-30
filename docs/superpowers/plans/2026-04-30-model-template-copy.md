# Model Template Copy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor model loading so global `agents/` acts as a template library only, with lazy copy-on-first-reference to world-private directories, plus a `sync-models` CLI command.

**Architecture:** `ModelResolver.resolve()` drops global fallback; new `ensure()` copies from template when missing. `WorldRegistry` simplifies to single-pass local scanning. `sync-models` compares global templates with world-private models, auto-copying new templates and interactively prompting on conflicts.

**Tech Stack:** Python 3.12, pytest, standard library (`pathlib`, `shutil`)

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/runtime/lib/exceptions.py` | Exception definitions (`ModelNotFoundError`) |
| `src/runtime/model_resolver.py` | Model resolution logic: `resolve()`, `ensure()`, copy helpers |
| `src/runtime/world_registry.py` | World loading orchestration; uses `ensure()` instead of `resolve()` |
| `src/cli/main.py` | CLI entry point; adds `sync-models` subcommand |
| `tests/runtime/test_model_resolver.py` | Unit tests for `ModelResolver` |

---

### Task 1: Add ModelNotFoundError Exception

**Files:**
- Modify: `src/runtime/lib/exceptions.py`
- Test: `tests/runtime/test_model_resolver.py` (will be used in Task 2)

- [ ] **Step 1: Write `ModelNotFoundError`**

Add to `src/runtime/lib/exceptions.py` after the existing exception classes:

```python
class ModelNotFoundError(RuntimeError):
    def __init__(self, model_id: str):
        self.model_id = model_id
        super().__init__(f"Model not found: {model_id}")
```

- [ ] **Step 2: Verify importable**

Run: `python -c "from src.runtime.lib.exceptions import ModelNotFoundError; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
rtk git add src/runtime/lib/exceptions.py
rtk git commit -m "feat: add ModelNotFoundError exception"
```

---

### Task 2: Refactor ModelResolver

**Files:**
- Modify: `src/runtime/model_resolver.py`
- Test: `tests/runtime/test_model_resolver.py`

- [ ] **Step 1: Write failing test for `resolve()` without global fallback**

In `tests/runtime/test_model_resolver.py`, replace the old `test_resolve_falls_back_to_global` and `test_resolve_no_world_agents_dir` with new tests. First, write the new test that expects `resolve()` to return `None` when model is only in global:

```python
def test_resolve_does_not_fallback_to_global(self, tmp_path: Path) -> None:
    """resolve() no longer falls back to global paths."""
    world_dir = tmp_path / "world"
    world_dir.mkdir()

    global_dir = tmp_path / "global"
    global_model_dir = global_dir / "ladle" / "model"
    global_model_dir.mkdir(parents=True)
    (global_model_dir / "model.yaml").write_text("name: global-ladle")

    resolver = ModelResolver(str(world_dir), [str(global_dir)])
    result = resolver.resolve("ladle")

    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_model_resolver.py::TestModelResolver::test_resolve_does_not_fallback_to_global -v`
Expected: FAIL (old code still falls back)

- [ ] **Step 3: Remove global fallback from `resolve()`**

Replace `src/runtime/model_resolver.py` with:

```python
"""ModelResolver: resolves a modelId to a model/ directory path."""

import shutil
from pathlib import Path

from src.runtime.lib.exceptions import ModelNotFoundError


class ModelResolver:
    """Resolves a modelId to a model/ directory path.

    Searches only in the world's private agents/ directory.
    Global paths are used only as templates for lazy copy via ensure().
    """

    def __init__(self, world_dir: str, global_paths: list[str]):
        """Initialize the resolver.

        Args:
            world_dir: Path to the world directory (e.g., "worlds/steel-plant-01")
            global_paths: List of paths to global model directories (e.g., ["agents/"])
        """
        self.world_dir = Path(world_dir)
        self.global_paths = [Path(p) for p in global_paths]
        self._shared_libs_copied: bool = False

    def resolve(self, model_id: str) -> Path | None:
        """Return the Path to the model/ directory, or None if not found.

        Searches world private agents only. No global fallback.
        """
        world_agents_dir = self.world_dir / "agents"
        if world_agents_dir.exists():
            return self._find_model_dir(world_agents_dir, model_id)
        return None

    def ensure(self, model_id: str) -> Path:
        """Guarantee model_id exists in world-private dir, copying from global templates if needed.

        1. resolve() locally -> found -> return.
        2. Find in global templates -> copy to world -> return.
        3. Not found anywhere -> ModelNotFoundError.
        """
        local = self.resolve(model_id)
        if local is not None:
            return local

        for global_path in self.global_paths:
            template = self._find_model_dir(global_path, model_id)
            if template is not None:
                self._copy_from_template(template, global_path)
                self._ensure_shared_libs()
                result = self.resolve(model_id)
                if result is not None:
                    return result

        raise ModelNotFoundError(model_id)

    @staticmethod
    def _find_model_dir(root: Path, model_id: str) -> Path | None:
        """Recursively search root for */{model_id}/model directory."""
        pattern = f"{model_id}/model"
        for match in root.rglob(pattern):
            if match.is_dir():
                return match
        return None

    def _copy_from_template(self, template_model_dir: Path, global_root: Path) -> None:
        """Copy model/ and libs/ from template agent dir to world agents/."""
        # template_model_dir is agents/{ns...}/{mid}/model/
        # template_agent_dir is agents/{ns...}/{mid}/
        template_agent_dir = template_model_dir.parent
        rel_path = template_agent_dir.relative_to(global_root)
        world_target = self.world_dir / "agents" / rel_path

        # Copy model/ directory
        world_model_dir = world_target / "model"
        self._copytree_skip_existing(template_model_dir, world_model_dir)

        # Copy libs/ directory if it exists in template
        template_libs_dir = template_agent_dir / "libs"
        if template_libs_dir.exists():
            world_libs_dir = world_target / "libs"
            self._copytree_skip_existing(template_libs_dir, world_libs_dir)

    def _ensure_shared_libs(self) -> None:
        """Copy agents/shared/libs/ to world on first ensure() call."""
        if self._shared_libs_copied:
            return
        self._shared_libs_copied = True

        for global_path in self.global_paths:
            shared_libs = global_path / "shared" / "libs"
            if shared_libs.exists():
                world_shared_libs = self.world_dir / "agents" / "shared" / "libs"
                self._copytree_skip_existing(shared_libs, world_shared_libs)
                break

    @staticmethod
    def _copytree_skip_existing(src: Path, dst: Path) -> None:
        """Recursively copy src to dst, skipping files that already exist."""
        if not src.exists():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            dst_item = dst / item.name
            if item.is_dir():
                ModelResolver._copytree_skip_existing(item, dst_item)
            else:
                if not dst_item.exists():
                    shutil.copy2(item, dst_item)
```

- [ ] **Step 4: Run all ModelResolver tests**

Run: `pytest tests/runtime/test_model_resolver.py -v`
Expected: Some tests fail (old fallback tests still exist and need updating)

- [ ] **Step 5: Update test file to match new behavior**

Replace `tests/runtime/test_model_resolver.py` entirely:

```python
"""Tests for ModelResolver."""

import pytest
from pathlib import Path

from src.runtime.model_resolver import ModelResolver
from src.runtime.lib.exceptions import ModelNotFoundError


class TestModelResolver:
    """Test suite for ModelResolver."""

    def test_resolve_in_world_agents(self, tmp_path: Path) -> None:
        """Test finding a model in the world's agents directory."""
        world_dir = tmp_path / "world"
        agents_dir = world_dir / "agents"
        model_dir = agents_dir / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_resolve_prefers_world_over_global(self, tmp_path: Path) -> None:
        """World-private models are found; global models are ignored by resolve()."""
        world_dir = tmp_path / "world"
        world_agents_dir = world_dir / "agents"
        world_model_dir = world_agents_dir / "ladle" / "model"
        world_model_dir.mkdir(parents=True)
        (world_model_dir / "model.yaml").write_text("name: world-ladle")

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == world_model_dir.resolve()

    def test_resolve_does_not_fallback_to_global(self, tmp_path: Path) -> None:
        """resolve() no longer falls back to global paths."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("ladle")

        assert result is None

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        """Test returning None when model is not found in world."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("nonexistent")

        assert result is None

    def test_resolve_no_world_agents_dir(self, tmp_path: Path) -> None:
        """Test that resolver handles missing world agents/ directory gracefully."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is None

    def test_resolve_model_in_flat_namespace(self, tmp_path: Path) -> None:
        """Test finding a model under a namespace subdirectory."""
        world_dir = tmp_path / "world"
        agents_dir = world_dir / "agents"
        model_dir = agents_dir / "namespace" / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_ensure_copies_from_global(self, tmp_path: Path) -> None:
        """ensure() copies global template to world when missing locally."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("ladle")

        assert result is not None
        assert result.resolve() == (world_dir / "agents" / "ladle" / "model").resolve()
        assert (world_dir / "agents" / "ladle" / "model" / "index.yaml").exists()

    def test_ensure_skips_existing_world_model(self, tmp_path: Path) -> None:
        """ensure() does not copy when world already has the model."""
        world_dir = tmp_path / "world"
        world_model_dir = world_dir / "agents" / "ladle" / "model"
        world_model_dir.mkdir(parents=True)
        (world_model_dir / "index.yaml").write_text("name: world-ladle")

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("ladle")

        assert result.resolve() == world_model_dir.resolve()
        content = (world_model_dir / "index.yaml").read_text()
        assert "world-ladle" in content

    def test_ensure_raises_when_not_found_anywhere(self, tmp_path: Path) -> None:
        """ensure() raises ModelNotFoundError when model is missing everywhere."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()
        global_dir = tmp_path / "global"
        global_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        with pytest.raises(ModelNotFoundError):
            resolver.ensure("nonexistent")

    def test_ensure_copies_shared_libs(self, tmp_path: Path) -> None:
        """ensure() copies shared/libs/ from global on first call."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")
        shared_libs = global_dir / "shared" / "libs"
        shared_libs.mkdir(parents=True)
        (shared_libs / "util.py").write_text("def hello(): pass")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        resolver.ensure("ladle")

        assert (world_dir / "agents" / "shared" / "libs" / "util.py").exists()

    def test_ensure_preserves_namespace_structure(self, tmp_path: Path) -> None:
        """ensure() preserves namespace path when copying from global."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "logistics" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("ladle")

        expected = world_dir / "agents" / "logistics" / "ladle" / "model"
        assert result.resolve() == expected.resolve()
```

- [ ] **Step 6: Run all ModelResolver tests**

Run: `pytest tests/runtime/test_model_resolver.py -v`
Expected: All 11 tests PASS

- [ ] **Step 7: Commit**

```bash
rtk git add src/runtime/model_resolver.py tests/runtime/test_model_resolver.py
rtk git commit -m "feat: ModelResolver with lazy template copy and ensure()"
```

---

### Task 3: Simplify WorldRegistry

**Files:**
- Modify: `src/runtime/world_registry.py`
- Test: `pytest tests/runtime/` (integration smoke test)

- [ ] **Step 1: Update `model_loader` to use `ensure()`**

In `src/runtime/world_registry.py`, replace the `model_loader` closure inside `load_world()`:

```python
# OLD:
def model_loader(model_id: str) -> dict | None:
    model_dir = resolver.resolve(model_id)
    if model_dir is not None:
        return ModelLoader.load(model_dir.parent)
    return None

# NEW:
def model_loader(model_id: str) -> dict | None:
    try:
        model_dir = resolver.ensure(model_id)
        return ModelLoader.load(model_dir.parent)
    except Exception as e:
        logger.warning("Model '%s' not found: %s", model_id, e)
        return None
```

- [ ] **Step 2: Simplify `agent_namespace_resolver`**

Replace the `agent_namespace_resolver` closure:

```python
# OLD:
def agent_namespace_resolver(model_id: str) -> str | None:
    model_dir = resolver.resolve(model_id)
    if model_dir is None:
        return None
    scan_roots = [world_agents_dir, *[Path(p) for p in self._global_model_paths]]
    for root in scan_roots:
        namespace = agent_namespace_for_path(model_dir, root, "model")
        if namespace is not None:
            return namespace
    return None

# NEW:
def agent_namespace_resolver(model_id: str) -> str | None:
    model_dir = resolver.resolve(model_id)
    if model_dir is None:
        return None
    return agent_namespace_for_path(model_dir, world_agents_dir, "model")
```

- [ ] **Step 3: Simplify `LibRegistry.scan`**

Replace the dual-scan loop:

```python
# OLD:
global_roots = [Path(path) for path in self._global_model_paths]
first_scan = True
for root in [*global_roots, world_agents_dir]:
    if not root.exists():
        continue
    lib_registry.scan(str(root), clear=first_scan)
    first_scan = False

# NEW:
if world_agents_dir.exists():
    lib_registry.scan(str(world_agents_dir), clear=True)
```

- [ ] **Step 4: Run runtime tests**

Run: `pytest tests/runtime/ -v`
Expected: All tests PASS (some fixtures may need adjustment; if failures, inspect and fix)

- [ ] **Step 5: Commit**

```bash
rtk git add src/runtime/world_registry.py
rtk git commit -m "refactor: WorldRegistry uses ensure(), single-pass LibRegistry scan"
```

---

### Task 4: Add sync-models CLI Command

**Files:**
- Modify: `src/cli/main.py`
- Test: Manual CLI invocation

- [ ] **Step 1: Add sync-models subcommand to CLI**

Replace `src/cli/main.py` entirely:

```python
import argparse
import shutil
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-studio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run worker process loading all worlds from base directory"
    )
    run_parser.add_argument(
        "--base-dir", required=True, help="Base directory containing world subdirectories"
    )
    run_parser.add_argument(
        "--supervisor-ws", default=None, help="Supervisor WebSocket URL to register with"
    )
    run_parser.add_argument(
        "--ws-port", type=int, default=None, help="Local WebSocket port to expose"
    )
    run_parser.add_argument(
        "--force-stop-on-shutdown",
        type=lambda x: x.lower() == "true",
        default=None,
        help="Force stop isolated scenes on shutdown",
    )
    run_parser.set_defaults(func=_run_command)

    inline_parser = subparsers.add_parser(
        "run-inline", help="Run multiple worlds in the current process"
    )
    inline_parser.add_argument(
        "--world-dir",
        action="append",
        required=True,
        help="Path to world directory (can be repeated)",
    )
    inline_parser.add_argument(
        "--supervisor-ws",
        default=None,
        help="Supervisor WebSocket URL for loopback registration",
    )
    inline_parser.set_defaults(func=_run_inline_command)

    sup_parser = subparsers.add_parser(
        "supervisor", help="Start the Supervisor management plane"
    )
    sup_parser.add_argument(
        "--base-dir", default="worlds", help="Base directory containing worlds"
    )
    sup_parser.add_argument(
        "--ws-port", type=int, default=8001, help="WebSocket port for runtime registration"
    )
    sup_parser.add_argument(
        "--http-port", type=int, default=8080, help="HTTP port for management API"
    )
    sup_parser.set_defaults(func=_supervisor_command)

    sync_parser = subparsers.add_parser(
        "sync-models", help="Synchronize global templates into world-private agents/"
    )
    sync_parser.add_argument(
        "--world-dir", required=True, help="Path to world directory"
    )
    sync_parser.add_argument(
        "--force", action="store_true", help="Force overwrite existing files"
    )
    sync_parser.set_defaults(func=_sync_models_command)

    args = parser.parse_args(argv)
    return args.func(args)


def _run_command(args):
    from src.worker.cli.run_command import run_world
    return run_world(
        base_dir=args.base_dir,
        supervisor_ws=args.supervisor_ws,
        ws_port=args.ws_port,
        force_stop_on_shutdown=args.force_stop_on_shutdown,
    )


def _run_inline_command(args):
    from src.worker.cli.run_inline import run_inline
    return run_inline(
        world_dirs=args.world_dir,
        supervisor_ws=args.supervisor_ws,
    )


def _supervisor_command(args):
    from src.supervisor.cli import supervisor_main
    return supervisor_main(args)


def _sync_models_command(args):
    return sync_models(args.world_dir, force=args.force)


def sync_models(world_dir: str, force: bool = False) -> int:
    """Synchronize global templates into world-private agents/."""
    from src.runtime.model_resolver import ModelResolver

    world_path = Path(world_dir)
    world_agents = world_path / "agents"

    # Discover global models
    global_paths = ["agents"]  # Default global path
    # TODO: read from config if available

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

    # Discover world models
    world_models: dict[str, Path] = {}
    if world_agents.exists():
        for model_dir in world_agents.rglob("*/model"):
            if not model_dir.is_dir():
                continue
            model_id = model_dir.parent.name
            world_models[model_id] = model_dir

    resolver = ModelResolver(str(world_dir), global_paths)
    any_changes = False

    for model_id, template_dir in sorted(global_models.items()):
        if model_id in world_models:
            print(f"[SYNC] {model_id}")
            changed = _sync_single_model(template_dir, world_models[model_id], force)
            any_changes = any_changes or changed
        else:
            print(f"[ADD] {model_id}")
            resolver._copy_from_template(template_dir, _find_global_root(template_dir, global_paths))
            any_changes = True

    private_models = set(world_models) - set(global_models)
    for model_id in sorted(private_models):
        print(f"[SKIP] {model_id} (world-private, no global template)")

    if not any_changes and not private_models:
        print("No changes needed.")
    return 0


def _find_global_root(template_dir: Path, global_paths: list[str]) -> Path:
    """Find which global root a template directory belongs to."""
    for gp_str in global_paths:
        gp = Path(gp_str)
        try:
            template_dir.relative_to(gp)
            return gp
        except ValueError:
            continue
    return Path(global_paths[0])


def _sync_single_model(template_dir: Path, world_dir: Path, force: bool) -> bool:
    """Sync a single model, returning True if any changes were made."""
    changed = False
    for src_file in template_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(template_dir)
        dst_file = world_dir / rel

        if not dst_file.exists():
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            print(f"  [ADD] {rel}")
            changed = True
            continue

        if force:
            shutil.copy2(src_file, dst_file)
            print(f"  [OVERWRITE] {rel}")
            changed = True
        else:
            answer = input(f"  Conflict: {rel}. Overwrite? [Y/n/a(ll)/s(kip)] ")
            ans = answer.strip().lower()
            if ans in ("y", ""):
                shutil.copy2(src_file, dst_file)
                print(f"  [OVERWRITE] {rel}")
                changed = True
            elif ans == "a":
                force = True
                shutil.copy2(src_file, dst_file)
                print(f"  [OVERWRITE] {rel}")
                changed = True
            # n or s -> skip
    return changed


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify CLI help works**

Run: `python -m src.cli.main sync-models --help`
Expected: Shows help for sync-models with `--world-dir` and `--force` options

- [ ] **Step 3: Manual smoke test**

Create a temp world and global template, then run sync:

```bash
# Setup
mkdir -p /tmp/test-sync/agents/logistics/ladle/model
mkdir -p /tmp/test-sync/worlds/demo
echo "name: ladle" > /tmp/test-sync/agents/logistics/ladle/model/index.yaml
echo "world_id: demo" > /tmp/test-sync/worlds/demo/world.yaml

# Run sync
python -m src.cli.main sync-models --world-dir /tmp/test-sync/worlds/demo
```

Expected output: `[ADD] ladle` and the model is copied.

- [ ] **Step 4: Commit**

```bash
rtk git add src/cli/main.py
rtk git commit -m "feat: add sync-models CLI command with interactive prompt and --force"
```

---

### Task 5: Final Verification

- [ ] **Step 1: Run all runtime tests**

Run: `pytest tests/runtime/ -v`
Expected: All PASS

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Final commit (if any fixes)**

If any test fixes were needed, commit them. Otherwise this task is complete.

---

## Summary

| # | Task | Files Changed | Key Change |
|---|------|---------------|------------|
| 1 | Add `ModelNotFoundError` | `src/runtime/lib/exceptions.py` | New exception class |
| 2 | Refactor `ModelResolver` | `src/runtime/model_resolver.py`, `tests/runtime/test_model_resolver.py` | `resolve()` drops fallback; `ensure()` copies from template |
| 3 | Simplify `WorldRegistry` | `src/runtime/world_registry.py` | Single-pass local scan; `ensure()` for model loading |
| 4 | Add `sync-models` CLI | `src/cli/main.py` | New subcommand with `--force` and interactive prompt |
| 5 | Final verification | All test files | Full test suite passes |
