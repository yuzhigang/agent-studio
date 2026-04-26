# Lib Namespace and Access Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor lib system: remove `readonly` from `@lib_function`, change agent namespace from `agent` to `group.agent`, and restrict `LibProxy` to only current-agent and shared libs.

**Architecture:** Three coordinated changes across `decorator`, `registry`, and `proxy`, plus fixture and test updates. Each change is mechanical and TDD-safe.

**Tech Stack:** Python 3.12+, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|--------------|
| `src/runtime/lib/decorator.py` | Modify | Remove `readonly` param from `@lib_function` |
| `src/runtime/lib/registry.py` | Modify | Use `group.agent` as namespace; update `reload_module` |
| `src/runtime/lib/proxy.py` | Modify | Reject cross-agent and full-path calls |
| `tests/fixtures/agents/shared/libs/api.py` | Modify | Remove `readonly=True` from decorators |
| `tests/fixtures/agents/shared/libs/utils.py` | Modify | Remove `readonly=True` from decorators |
| `tests/fixtures/agents/logistics/ladle/libs/dispatcher.py` | Modify | Remove `readonly=True` from decorators |
| `tests/fixtures/agents/machines/converter/libs/planner.py` | Modify | Remove `readonly=True` from decorators |
| `tests/fixtures/agents/roles/ladle_dispatcher/libs/ladle.py` | Modify | Remove `readonly=True` from decorators |
| `tests/fixtures/agents_bad_namespace/logistics/converter/libs/planner.py` | Modify | Remove `readonly=True` from decorators |
| `tests/runtime/lib/test_registry.py` | Modify | Update scan/lookup tests for `group.agent` |
| `tests/runtime/lib/test_proxy.py` | Modify | Update proxy tests for access control |
| `docs/superpowers/specs/2026-04-14-agent-studio-script-lib-design.md` | Modify | `scripts/` → `libs/` |

---

### Task 1: Remove `readonly` from `@lib_function` and all fixtures

**Files:**
- Modify: `src/runtime/lib/decorator.py`
- Modify: `tests/fixtures/agents/shared/libs/api.py`
- Modify: `tests/fixtures/agents/shared/libs/utils.py`
- Modify: `tests/fixtures/agents/logistics/ladle/libs/dispatcher.py`
- Modify: `tests/fixtures/agents/machines/converter/libs/planner.py`
- Modify: `tests/fixtures/agents/roles/ladle_dispatcher/libs/ladle.py`
- Modify: `tests/fixtures/agents_bad_namespace/logistics/converter/libs/planner.py`

**Context:** The `readonly` parameter in `@lib_function` is accepted but never read by any code. It should be removed to keep the API clean.

- [ ] **Step 1: Write the failing test (to confirm `readonly` still accepted)**

Create a temporary test file at `/tmp/test_readonly_removed.py` (do NOT add to repo):

```python
from src.runtime.lib.decorator import lib_function

# This should FAIL after we remove readonly
try:
    @lib_function(name="foo", namespace="test", readonly=True)
    def foo(args):
        return args
    print("PASS: readonly still accepted")
except TypeError as e:
    print(f"FAIL: {e}")
```

Run: `python /tmp/test_readonly_removed.py`
Expected: `PASS: readonly still accepted`

- [ ] **Step 2: Remove `readonly` from `decorator.py`**

Replace the entire file `src/runtime/lib/decorator.py`:

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

- [ ] **Step 3: Remove `readonly=True` from all fixture files**

Use `replace_all` in each file:

1. `tests/fixtures/agents/shared/libs/api.py`: Replace `@lib_function(name="echo", namespace="shared", readonly=True)` → `@lib_function(name="echo", namespace="shared")`
2. `tests/fixtures/agents/shared/libs/api.py`: Replace `@lib_function(name="httpGet", namespace="shared", readonly=True)` → `@lib_function(name="httpGet", namespace="shared")`
3. `tests/fixtures/agents/shared/libs/utils.py`: Replace `@lib_function(name="uppercase", namespace="shared", readonly=True)` → `@lib_function(name="uppercase", namespace="shared")`
4. `tests/fixtures/agents/logistics/ladle/libs/dispatcher.py`: Replace `@lib_function(name="getCandidates", namespace="ladle", readonly=True)` → `@lib_function(name="getCandidates", namespace="ladle")`
5. `tests/fixtures/agents/machines/converter/libs/planner.py`: Replace `@lib_function(name="plan", namespace="converter", readonly=True)` → `@lib_function(name="plan", namespace="converter")`
6. `tests/fixtures/agents/roles/ladle_dispatcher/libs/ladle.py`: Replace `@lib_function(name="getCandidates", namespace="ladle_dispatcher", readonly=True)` → `@lib_function(name="getCandidates", namespace="ladle_dispatcher")`
7. `tests/fixtures/agents_bad_namespace/logistics/converter/libs/planner.py`: Replace `@lib_function(name="plan", namespace="wrong", readonly=True)` → `@lib_function(name="plan", namespace="wrong")`

- [ ] **Step 4: Verify `readonly` is now rejected**

Run: `python /tmp/test_readonly_removed.py`
Expected: `FAIL: lib_function() got an unexpected keyword argument 'readonly'`

- [ ] **Step 5: Run all lib tests to ensure no regressions**

Run: `pytest tests/runtime/lib/ -v`
Expected: All tests still PASS (registry tests use internal `_data` manipulation, not actual `@lib_function` decorators, so they should be unaffected at this stage).

- [ ] **Step 6: Commit**

```bash
git add src/runtime/lib/decorator.py tests/fixtures/
git commit -m "refactor: remove unused readonly from @lib_function and fixtures"
```

---

### Task 2: Change agent namespace from `agent` to `group.agent`

**Files:**
- Modify: `src/runtime/lib/registry.py`
- Modify: `tests/runtime/lib/test_registry.py`
- Modify: `tests/fixtures/agents/machines/converter/libs/planner.py`
- Modify: `tests/fixtures/agents/roles/ladle_dispatcher/libs/ladle.py`

**Context:** Currently `LibRegistry.scan` uses `agent_dir.name` as namespace (e.g., `ladle`). This causes conflicts when different groups have agents with the same name. Change to `f"{group_dir.name}.{agent_dir.name}"` (e.g., `logistics.ladle`).

The `@lib_function` decorator validates that `declared_ns == file_ns`. So if a file under `logistics/ladle/libs/` declares `namespace="ladle"`, it will now mismatch because file_ns is `logistics.ladle`. We must update fixture files to declare the correct full namespace.

**Fixture namespace updates:**
- `logistics/ladle/libs/dispatcher.py`: `namespace="ladle"` → `namespace="logistics.ladle"`
- `machines/converter/libs/planner.py`: `namespace="converter"` → `namespace="machines.converter"`
- `roles/ladle_dispatcher/libs/ladle.py`: `namespace="ladle_dispatcher"` → `namespace="roles.ladle_dispatcher"`
- `shared/libs/api.py`: stays `namespace="shared"` (shared is special, not under a group)
- `shared/libs/utils.py`: stays `namespace="shared"`

- [ ] **Step 1: Write the failing test**

Replace `tests/runtime/lib/test_registry.py` with:

```python
import os
import pytest
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError, LibRegistrationError

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def test_registry_scan_uses_group_agent_namespace(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    # logistics/ladle/libs/dispatcher.py declares namespace="logistics.ladle"
    func = registry.lookup("logistics.ladle", "dispatcher", "getCandidates")
    assert func({"x": 1}) == {"candidates": []}

    # shared/libs/utils.py declares namespace="shared"
    func = registry.lookup("shared", "utils", "uppercase")
    assert func({"text": "hello"}) == {"text": "HELLO"}


def test_registry_lookup_old_namespace_missing(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    # Old namespace "ladle" should no longer exist
    with pytest.raises(LibNotFoundError):
        registry.lookup("ladle", "dispatcher", "getCandidates")


def test_registry_namespace_mismatch_raises():
    reg = LibRegistry()
    agents_dir = os.path.join(FIXTURES, "agents_bad_namespace")
    with pytest.raises(LibRegistrationError):
        reg.scan(agents_dir)
```

Run: `pytest tests/runtime/lib/test_registry.py -v`
Expected: FAIL — `test_registry_scan_uses_group_agent_namespace` fails because registry still uses old `agent` namespace, and fixture declares `namespace="ladle"` which now mismatches.

- [ ] **Step 2: Update `LibRegistry.scan`**

In `src/runtime/lib/registry.py`, find the `scan` method:

```python
            # Handle grouped agents: agents/<group>/<agent>/libs/
            for group_dir in agents_path.iterdir():
                if not group_dir.is_dir() or group_dir.name == "shared":
                    continue
                for agent_dir in group_dir.iterdir():
                    if not agent_dir.is_dir():
                        continue
                    libs_dir = agent_dir / "libs"
                    if not libs_dir.exists():
                        continue
                    namespace = agent_dir.name
```

Replace `namespace = agent_dir.name` with:
```python
                    namespace = f"{group_dir.name}.{agent_dir.name}"
```

- [ ] **Step 3: Update `LibRegistry.reload_module`**

In `src/runtime/lib/registry.py`, find:

```python
        if parts[0] == "shared" and parts[1] == "libs":
            namespace = "shared"
        else:
            namespace = parts[1]  # agent name
```

Replace with:
```python
        if parts[0] == "shared" and parts[1] == "libs":
            namespace = "shared"
        else:
            namespace = f"{parts[0]}.{parts[1]}"  # group.agent
```

- [ ] **Step 4: Update fixture namespace declarations**

1. `tests/fixtures/agents/logistics/ladle/libs/dispatcher.py`: Replace `namespace="ladle"` → `namespace="logistics.ladle"`
2. `tests/fixtures/agents/machines/converter/libs/planner.py`: Replace `namespace="converter"` → `namespace="machines.converter"`
3. `tests/fixtures/agents/roles/ladle_dispatcher/libs/ladle.py`: Replace `namespace="ladle_dispatcher"` → `namespace="roles.ladle_dispatcher"`

- [ ] **Step 5: Run registry tests**

Run: `pytest tests/runtime/lib/test_registry.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 6: Run full lib test suite**

Run: `pytest tests/runtime/lib/ -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/runtime/lib/registry.py tests/runtime/lib/test_registry.py tests/fixtures/
git commit -m "feat: use group.agent namespace in LibRegistry"
```

---

### Task 3: Enforce LibProxy access control (no cross-agent, no full path)

**Files:**
- Modify: `src/runtime/lib/proxy.py`
- Modify: `tests/runtime/lib/test_proxy.py`

**Context:** `LibProxyNode.__call__` currently accepts:
- 2-segment: `lib.module.name` (current agent, via default_namespace)
- 3+ segment: `lib.xxx.yyy.zzz` (any full path)

We need to restrict to:
- 2-segment: `lib.module.name` (current agent)
- 3-segment where first segment is `shared`: `lib.shared.module.name`
- Everything else: raise `LibNotFoundError`

- [ ] **Step 1: Write the failing test**

Replace `tests/runtime/lib/test_proxy.py` with:

```python
import pytest
from src.runtime.lib.proxy import LibProxy
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError


def test_proxy_omit_default_namespace(registry: LibRegistry):
    registry._data["logistics.ladle.dispatcher.getCandidates"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    result = proxy.dispatcher.getCandidates({})
    assert result == {"ok": True}


def test_proxy_shared_namespace(registry: LibRegistry):
    registry._data["shared.data_adapter.transform"] = lambda args: args
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    result = proxy.shared.data_adapter.transform({"x": 1})
    assert result == {"x": 1}


def test_proxy_cross_agent_rejected(registry: LibRegistry):
    registry._data["machines.converter.planner.plan"] = lambda args: args
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    with pytest.raises(LibNotFoundError, match="cross-agent"):
        proxy.machines.converter.planner.plan({})


def test_proxy_full_path_rejected(registry: LibRegistry):
    registry._data["logistics.ladle.dispatcher.getCandidates"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    with pytest.raises(LibNotFoundError, match="cross-agent"):
        proxy.logistics.ladle.dispatcher.getCandidates({})


def test_proxy_missing_raises():
    registry = LibRegistry()
    registry.clear()
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    with pytest.raises(LibNotFoundError):
        proxy.missing.func({})
```

Run: `pytest tests/runtime/lib/test_proxy.py -v`
Expected: FAIL — `test_proxy_cross_agent_rejected` and `test_proxy_full_path_rejected` fail because current proxy allows any full path.

- [ ] **Step 2: Update `LibProxyNode.__call__`**

In `src/runtime/lib/proxy.py`, replace the `__call__` method with:

```python
    def __call__(self, *args, **kwargs):
        if len(self._path) < 2:
            raise LibNotFoundError(".".join(self._path), details="incomplete path")

        if len(self._path) == 2:
            # lib.module.name → default_namespace.module.name
            if not self._default_namespace:
                raise LibNotFoundError(".".join(self._path), details="no default namespace")
            candidates = [f"{self._default_namespace}.{self._path[0]}.{self._path[1]}"]
        elif len(self._path) == 3 and self._path[0] == "shared":
            # lib.shared.module.name
            candidates = [".".join(self._path)]
        else:
            raise LibNotFoundError(".".join(self._path), details="cross-agent lib calls are not allowed")

        func = None
        for key in candidates:
            func = self._registry._data.get(key)
            if func is not None:
                break

        if func is None:
            raise LibNotFoundError(".".join(self._path), details="not registered")

        # Inject LibContext into bound method's instance
        instance = getattr(func, '__self__', None)
        if instance and self._lib_context is not None:
            instance._context = self._lib_context

        return func(*args, **kwargs)
```

- [ ] **Step 3: Run proxy tests**

Run: `pytest tests/runtime/lib/test_proxy.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 4: Run full lib test suite**

Run: `pytest tests/runtime/lib/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/proxy.py tests/runtime/lib/test_proxy.py
git commit -m "feat: restrict LibProxy to current-agent and shared libs only"
```

---

### Task 4: Update design doc (scripts → libs)

**Files:**
- Modify: `docs/superpowers/specs/2026-04-14-agent-studio-script-lib-design.md`

**Context:** The original design doc uses `scripts/` directory but the codebase uses `libs/`. Update all occurrences.

- [ ] **Step 1: Replace `scripts/` with `libs/` throughout the doc**

Use `replace_all` on `docs/superpowers/specs/2026-04-14-agent-studio-script-lib-design.md`:

Replace all occurrences of `scripts/` with `libs/`.
Replace all occurrences of `/scripts` with `/libs`.

Also update the directory tree example (section 3.1):
```
agents/
├── ladle/
│   ├── model.json
│   └── libs/
│       ├── dispatcher.py
│       └── validator.py
```

And update the text:
- "每个 `agents/<model>/scripts/` 目录" → "每个 `agents/<model>/libs/` 目录"
- "`agents/shared/scripts/` 目录" → "`agents/shared/libs/` 目录"
- "agents/<namespace>/scripts/" → "agents/<namespace>/libs/"

- [ ] **Step 2: Verify no `scripts/` remains**

Run: `grep -n "scripts" docs/superpowers/specs/2026-04-14-agent-studio-script-lib-design.md`
Expected: No matches (or only in historical/context sections that intentionally reference the old name).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-14-agent-studio-script-lib-design.md
git commit -m "docs: align script lib design doc with libs/ directory convention"
```

---

## Self-Review

### 1. Spec coverage

| Spec Requirement | Task |
|---|---|
| Remove `readonly` from `@lib_function` | Task 1 |
| Remove `readonly` from all fixtures | Task 1 |
| `LibRegistry.scan` uses `group.agent` namespace | Task 2 |
| `LibRegistry.reload_module` uses `group.agent` namespace | Task 2 |
| Update fixture namespace declarations to match | Task 2 |
| `LibProxy` rejects cross-agent calls | Task 3 |
| `LibProxy` rejects explicit full path calls | Task 3 |
| `LibProxy` allows 2-segment (current agent) | Task 3 |
| `LibProxy` allows `lib.shared.xxx` | Task 3 |
| Design doc says `libs/` instead of `scripts/` | Task 4 |

No gaps.

### 2. Placeholder scan

- No "TBD", "TODO", "implement later" found.
- All test code is explicit with complete assertions.
- All implementation code is complete.
- No "similar to Task N" shortcuts.

### 3. Type consistency

- `lib_function(*, name: str, namespace: str | None = None)` — consistent after `readonly` removal
- `LibRegistry.lookup(namespace, module, name)` — signature unchanged
- `LibProxy(default_namespace=...)` — signature unchanged
- `schedule_cron` not involved in this plan

All consistent. Plan is ready.
