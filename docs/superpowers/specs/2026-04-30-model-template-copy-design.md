# Model Template Copy Design

> Agent-level model definitions as templates, auto-copied to world on first load.

- **Status**: Draft
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

**Global agents/ is a template library only.** Each world owns a private copy of
every model it uses, copied from the global template on first reference (lazy
copy). After copy, the world's copy is the sole source of truth. There is no
runtime fallback to global agents.

### Scope

- **Copy on**: `load_world()`, when a `modelId` referenced by an instance
  declaration is not found in the world's private `agents/` directory.
- **Copy what**: `model/` directory and `libs/` directory (if present) from the
  template agent directory. `shared/libs/` is **always** copied.
- **Directory structure preserved**: namespace path is maintained (e.g.,
  `agents/logistics/ladle/model/` → `worlds/{id}/agents/logistics/ladle/model/`).
- **Existing files never overwritten**: if the target path already has a file,
  it is skipped. This ensures world-local customizations are never silently
  replaced.

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
        self._copied: set[str] = set()  # track already-copied modelIds

    def resolve(self, model_id: str) -> Path | None:
        """Search world-private agents/ only. No global fallback."""
        ...

    def ensure(self, model_id: str) -> Path:
        """Guarantee model_id exists in world-private dir, copying from
        global templates if needed.

        1. resolve() locally → found → return.
        2. Already in _copied but deleted → ModelNotFoundError.
        3. Find in global templates → copy to world → _copied += 1 → return.
        4. Not found anywhere → ModelNotFoundError.
        """
        ...
```

**Removed behavior**: `resolve()` no longer falls back to global paths.

**Copy logic** (`_copy_from_template`):

```
Input: template_path (path to model/ dir in global agents/)
1. Compute relative path from global root to agent dir
2. Copy agent_dir/model/ → world_agents/{rel}/model/   (skip existing)
3. Copy agent_dir/libs/ → world_agents/{rel}/libs/      (skip existing, if exists)
4. Copy shared/libs/ → world_agents/shared/libs/        (skip existing)
```

### 2. WorldRegistry.load_world()

Simplifies several closures since models are guaranteed local.

**model_loader**:
```python
def model_loader(model_id: str) -> dict | None:
    try:
        model_dir = resolver.ensure(model_id)  # auto-copy if needed
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

`_copytree_if_not_exists(src, dst)`:
- Create `dst` directory if not exists.
- For each file in `src`: copy to `dst` only if `dst/file` does NOT exist.
- Recurse into subdirectories.
- This ensures world-local model customizations are never overwritten.

### 4. shared/libs/ Handling

`agents/shared/libs/` is a special case: it contains libraries that any model
may reference at runtime. On first `ensure()` call in a world:

1. Check if `world_agents/shared/libs/` exists.
2. If not, copy from `agents/shared/libs/`.
3. If partially present, merge (skip existing files).

This is done only once per world (tracked by `_copied` set reaching
`shared/libs/`).

## Error Handling

| Scenario | Behavior |
|---|---|
| modelId not in world or global | `ModelNotFoundError` → instance declaration skipped (log warning) |
| Copied model deleted from world | `ModelNotFoundError` on re-load (_copied acts as guard) |
| File conflict during copy | Skipped (`_copytree_if_not_exists`) |
| shared/libs/ partially exists | Merge (only missing files copied) |
| Concurrent load of same world | `WorldLock` ensures mutual exclusion |
| Template libs/ does not exist | Skipped, no error |

## Testing

### Unit Tests (ModelResolver)

1. `resolve()` on world-private model → returns path.
2. `resolve()` on global-only model → returns None (no fallback).
3. `ensure()` on world-private model → returns path, no copy.
4. `ensure()` on global-only model → copies to world, returns world path.
5. `ensure()` on non-existent model → `ModelNotFoundError`.
6. `ensure()` on previously-copied but deleted model → `ModelNotFoundError`.
7. Copy preserves directory structure (namespace path).
8. `shared/libs/` is always copied on first `ensure()`.
9. Existing files in world are not overwritten during copy.

### Integration Tests (WorldRegistry)

1. `load_world()` with global-only model reference → model auto-copied, world
   loads successfully.
2. `load_world()` with non-existent model reference → instance skipped, warning
   logged, world loads.
3. After load, other worlds referencing the same model get their own copies
   (isolation).

### Test Updates

- Update `test_model_resolver.py`: remove "falls back to global" tests; add
  "resolve does not fallback" and "ensure copies from global" tests.
- World test fixtures may need to pre-populate world-private models.

## Files to Change

| File | Change |
|---|---|
| `src/runtime/model_resolver.py` | New `ensure()`, `_copy_from_template()`, `_copytree_if_not_exists()`; `resolve()` drops global fallback |
| `src/runtime/lib/exceptions.py` | Add `ModelNotFoundError` (or reuse existing) |
| `src/runtime/world_registry.py` | Simplify `model_loader`, `agent_namespace_resolver`, `LibRegistry.scan` |
| `tests/runtime/test_model_resolver.py` | Add ensure tests; remove fallback tests |

## Non-Goals

- `create_world()` remains unchanged (no model dependency declaration needed).
- `ModelLoader` is unchanged (still loads from a `model/` directory).
- `InstanceLoader` is unchanged (still scans `instances/` in world).
- No symlinks or CoW filesystem features.
- No special tooling for "updating templates in existing worlds".
