# Model Template Copy Design

> Agent-level model definitions as templates, auto-copied to world on first reference.

- **Status**: Approved
- **Date**: 2026-04-30
- **Author**: Claude

## Problem

The current model resolution system has unclear priority between per-world and
global agent model definitions:

- `ModelResolver` searches world-private `agents/` first, then falls back to
  global paths. This creates implicit runtime dependencies on global templates.
- Changes to global templates can silently affect existing worlds.
- The subscription model is unclear: global agents are templates vs. sources of
  truth vs. fallback libraries.

## Design

### Principle

**Global `agents/` is a template library only.** Each world owns a private copy of
every model it uses, copied from the global template on first reference (lazy
copy). After copy, the world's copy is the sole source of truth. There is no
runtime fallback to global agents.

Worlds may also contain **world-private models** that have no corresponding
global template. These are owned entirely by the world and are never touched by
the template copy mechanism.

### Scope

- **Copy on**: `load_world()`, when a `modelId` referenced by an instance
declaration is not found in the world's private `agents/` directory.
- **Copy what**: `model/` directory and `libs/` directory (if present) from the
template agent directory. `shared/libs/` is **always** copied.
- **Directory structure preserved**: namespace path is maintained (e.g.,
`agents/logistics/ladle/model/` -> `worlds/{id}/agents/logistics/ladle/model/`).
- **Existing files never overwritten**: if the target path already has a file,
it is skipped. This ensures world-local customizations are never silently
replaced.

### Sync-Models Command

An explicit CLI command `sync-models` is provided to update existing worlds when
global templates change:

```bash
python -m src.cli.main sync-models --world-dir <path> [--force]
```

Behavior:
- Scans all global templates and compares with the world's private `agents/`.
- **Global has, world missing**: auto-copies the new template to the world.
- **Global has, world has**: conflict. By default, interactively prompts the user
  for each conflicting file (`[Y/n/a/s]`). With `--force`, overwrites all conflicts.
- **World has, global missing**: world-private model. Completely skipped.

## Architecture Changes

### 1. ModelResolver

The core of the change. `resolve()` becomes world-private only. A new
`ensure()` method handles lazy copy from global templates.

**New methods**:

```python
class ModelNotFoundError(Exception):
    """Raised when a modelId cannot be found in world or global templates."""

class ModelResolver:
    def __init__(self, world_dir: str, global_paths: list[str]):
        ...
        self._shared_libs_copied: bool = False  # shared/libs/ copied once

    def resolve(self, model_id: str) -> Path | None:
        """Search world-private agents/ only. No global fallback."""
        ...

    def ensure(self, model_id: str) -> Path:
        """Guarantee model_id exists in world-private dir, copying from
        global templates if needed.

        1. resolve() locally -> found -> return.
        2. Find in global templates -> copy to world -> return.
        3. Not found anywhere -> ModelNotFoundError.
        """
        ...
```

**Removed behavior**: `resolve()` no longer falls back to global paths.

**Copy logic** (`_copy_from_template`):

The function receives `template_path` (the `model/` subdirectory in global
agents/). It uses `template_path.parent` to get the agent-level directory for
copying `model/` and `libs/`:

```
Input: template_path (Path to agents/{ns...}/{mid}/model/)
1. Compute relative path from global root to agent dir
   (template_path.parent relative to global root)
2. Copy template_path/* -> world_agents/{rel}/model/*   (skip existing)
3. Copy template_path.parent/libs/* -> world_agents/{rel}/libs/*
   (skip existing, if agent_dir/libs/ exists)
4. Copy shared/libs/ -> world_agents/shared/libs/        (skip existing)
```

### 2. WorldRegistry.load_world()

Simplifies several closures since models are guaranteed local.

**model_loader**:
```python
def model_loader(model_id: str) -> dict | None:
    try:
        model_dir = resolver.ensure(model_id)  # auto-copy if needed
        # ensure() returns Path to model/ subdirectory.
        # ModelLoader.load() expects the agent (parent) directory path,
        # so we pass model_dir.parent.
        return ModelLoader.load(model_dir.parent)
    except ModelNotFoundError:
        logger.warning(...)
        return None
```

**agent_namespace_resolver**: No longer scans global paths. Only resolves
namespace from the world's private `agents/` directory.

**LibRegistry scan**: Only scans `world_agents/` (since all needed libs are
already copied there). No longer needs dual-scan (global first, then world).

### 3. File Copy Semantics

`_copytree_skip_existing(src, dst)`:
- Create `dst` directory if not exists.
- For each file in `src`: copy to `dst` only if `dst/file` does NOT exist.
- Recurse into subdirectories.
- This ensures world-local model customizations are never overwritten.

### 4. shared/libs/ Handling

`agents/shared/libs/` is a special case: it contains libraries that any model
may reference at runtime. On first `ensure()` call in a world:

1. Check if `world_agents/shared/libs/` exists.
2. If not, copy from `agents/shared/libs/`.
3. If partially present, merge (only missing files copied).

This is done only once per world (tracked by `_shared_libs_copied` boolean
flag on ModelResolver).

### 5. sync-models Implementation

```python
def sync_models(world_dir: str, force: bool = False):
    """Synchronize global templates into world-private agents/."""
    ...
```

Three-way classification:
- **Global only**: auto-copy to world.
- **Global + World**: sync with conflict handling (interactive or force).
- **World only**: world-private model, completely skipped.

Interactive prompt per conflicting file:
```
Conflict: index.yaml. Overwrite? [Y/n/a(ll)/s(kip)]
```

## Error Handling

| Scenario | Behavior |
|---|---|
| modelId not in world or global | `ModelNotFoundError` -> instance declaration skipped (log warning) |
| Copied model deleted from world | Next `load_world()` re-copies from global template |
| File conflict during copy (ensure) | Skipped (`_copytree_skip_existing`) |
| File conflict during sync (no force) | Interactive prompt |
| File conflict during sync (force) | Overwritten |
| shared/libs/ partially exists | Merge (only missing files copied) |
| Concurrent load of same world | `WorldLock` ensures mutual exclusion |
| Template libs/ does not exist | Skipped, no error |
| World-private model (no global template) | Ignored by sync-models |

## Testing

### Unit Tests (ModelResolver)

1. `resolve()` on world-private model -> returns path.
2. `resolve()` on global-only model -> returns `None` (no fallback).
3. `ensure()` on world-private model -> returns path, no copy.
4. `ensure()` on global-only model -> copies to world, returns world path.
5. `ensure()` on non-existent model -> `ModelNotFoundError`.
6. `ensure()` called twice on same model -> returns path, does not copy twice.
7. Copy preserves directory structure (namespace path).
8. `shared/libs/` is always copied on first `ensure()`.
9. Existing files in world are not overwritten during `ensure()` copy.

### Integration Tests (WorldRegistry)

10. `load_world()` with global-only model reference -> model auto-copied, world
    loads successfully.
11. `load_world()` with non-existent model reference -> instance skipped, warning
    logged, world loads.
12. After load, other worlds referencing the same model get their own copies
    (isolation).

### sync-models Tests

13. `sync-models` with new global template -> auto-copied to world.
14. `sync-models --force` -> overwrites all conflicting files.
15. `sync-models` without force -> interactively prompts (mock `input`).
16. `sync-models` skips world-private models (no global template).

### Test Updates

- Update `test_model_resolver.py`: remove "falls back to global" tests; add
  "resolve does not fallback" and "ensure copies from global" tests.
- World test fixtures may need to pre-populate world-private models.

## Files to Change

| File | Change |
|---|---|
| `src/runtime/model_resolver.py` | New `ensure()`, `_copy_from_template()`, `_copytree_skip_existing()`; `resolve()` drops global fallback |
| `src/runtime/lib/exceptions.py` | Add `ModelNotFoundError` (or reuse existing) |
| `src/runtime/world_registry.py` | Simplify `model_loader`, `agent_namespace_resolver`, `LibRegistry.scan` |
| `src/cli/main.py` | Add `sync-models` subcommand |
| `tests/runtime/test_model_resolver.py` | Add ensure tests; remove fallback tests |

## Non-Goals

- `create_world()` remains unchanged (no model dependency declaration needed).
- `ModelLoader` is unchanged (still loads from a `model/` directory).
- `InstanceLoader` is unchanged (still scans `instances/` in world).
- No symlinks or CoW filesystem features.
- No automatic background sync (sync is always explicit via CLI).
