# Agent Studio Script Lib Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `lib` script library system: `@lib_function` decorator, `LibRegistry` scanner, `LibProxy` DSL object, and `SandboxExecutor` with a restricted builtins whitelist.

**Architecture:** A registry-based module discovery system that scans `agents/<model>/libs/` and `agents/shared/libs/`, collecting `@lib_function`-decorated functions into a namespaced registry. A chainable `LibProxy` resolves DSL calls like `lib.ladle.dispatcher.getCandidates(args)` at runtime. The `SandboxExecutor` runs JSON-embedded Python libs via `exec()` with a filtered `__builtins__` whitelist.

**Tech Stack:** Python 3.11+, pytest, watchdog (for hot reload), standard library only for core.

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/runtime/lib/exceptions.py` | All exception types: `LibNotFoundError`, `LibExecutionError`, `LibRegistrationError`, `ScriptExecutionError`, `ImmutableContextError` |
| `src/runtime/lib/decorator.py` | `@lib_function` decorator and internal metadata tracking |
| `src/runtime/lib/registry.py` | `LibRegistry` singleton: scan, register, lookup, reload with RLock |
| `src/runtime/lib/proxy.py` | `LibProxy` chainable DSL object that resolves calls against `LibRegistry` |
| `src/runtime/lib/sandbox.py` | `SandboxExecutor` that runs Python strings with restricted globals and builtins whitelist |
| `src/runtime/lib/__init__.py` | Public exports |
| `tests/runtime/lib/test_*.py` | Unit tests for each module |

---

### Task 1: Exception types

**Files:**
- Create: `src/runtime/lib/exceptions.py`
- Test: `tests/runtime/lib/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

```python
from src.runtime.lib.exceptions import (
    LibNotFoundError,
    LibExecutionError,
    LibRegistrationError,
    ScriptExecutionError,
    ImmutableContextError,
    LibValidationError,
)

def test_exceptions_are_runtime_error_subclasses():
    assert issubclass(LibNotFoundError, RuntimeError)
    assert issubclass(LibExecutionError, RuntimeError)
    assert issubclass(LibRegistrationError, RuntimeError)
    assert issubclass(ScriptExecutionError, RuntimeError)
    assert issubclass(ImmutableContextError, RuntimeError)
    assert issubclass(LibValidationError, RuntimeError)

def test_lib_not_found_error_carries_details():
    e = LibNotFoundError("foo.bar", details="not registered")
    assert e.name == "foo.bar"
    assert "not registered" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_exceptions.py -v`
Expected: `ModuleNotFoundError: No module named 'src.runtime.lib.exceptions'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/lib/exceptions.py
class LibNotFoundError(RuntimeError):
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        super().__init__(f"Lib not found: {name} ({details})")


class LibExecutionError(RuntimeError):
    def __init__(self, name: str, message: str = "", traceback: str = ""):
        self.name = name
        self.message = message
        self.traceback = traceback
        super().__init__(f"Lib execution failed: {name}: {message}")


class LibRegistrationError(RuntimeError):
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        super().__init__(f"Lib registration error: {name} ({details})")


class ScriptExecutionError(RuntimeError):
    def __init__(self, message: str = "", line: int | None = None):
        self.message = message
        self.line = line
        super().__init__(f"Script execution error (line {line}): {message}")


class ImmutableContextError(RuntimeError):
    def __init__(self, operation: str = ""):
        self.operation = operation
        super().__init__(f"Immutable context: {operation} is not allowed")


class LibValidationError(RuntimeError):
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        super().__init__(f"Lib validation error: {name} ({details})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_exceptions.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/exceptions.py tests/runtime/lib/test_exceptions.py
git commit -m "feat: add lib exception types"
```

---

### Task 2: `@lib_function` decorator

**Files:**
- Create: `src/runtime/lib/decorator.py`
- Test: `tests/runtime/lib/test_decorator.py`

- [ ] **Step 1: Write the failing test**

```python
from src.runtime.lib.decorator import lib_function

def test_decorator_attaches_metadata():
    @lib_function(name="getCandidates", namespace="ladle", readonly=True)
    def get_candidates(args: dict) -> dict:
        return {"ok": True}

    assert hasattr(get_candidates, "_lib_meta")
    assert get_candidates._lib_meta["name"] == "getCandidates"
    assert get_candidates._lib_meta["namespace"] == "ladle"
    assert get_candidates._lib_meta["readonly"] is True
    assert get_candidates._lib_meta["entrypoint"] == "get_candidates"

def test_decorator_defaults():
    @lib_function(name="doWork", namespace="shared")
    def do_work(args: dict) -> dict:
        return {}

    assert do_work._lib_meta["readonly"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_decorator.py -v`
Expected: `ModuleNotFoundError: No module named 'src.runtime.lib.decorator'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/lib/decorator.py
import functools


def lib_function(*, name: str, namespace: str, readonly: bool = False):
    def decorator(func):
        func._lib_meta = {
            "name": name,
            "namespace": namespace,
            "readonly": readonly,
            "entrypoint": func.__name__,
            "func": func,
        }
        return func
    return decorator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_decorator.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/decorator.py tests/runtime/lib/test_decorator.py
git commit -m "feat: add @lib_function decorator"
```

---

### Task 3: `LibRegistry`

**Files:**
- Create: `src/runtime/lib/registry.py`
- Test: `tests/runtime/lib/test_registry.py`
- Create sample fixture: `tests/fixtures/agents/ladle/libs/dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
import os
import sys
import pytest
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError, LibRegistrationError

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")

def test_registry_scan_and_lookup(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    func = registry.lookup("ladle", "dispatcher", "getCandidates")
    assert func({"x": 1}) == {"candidates": []}

def test_registry_lookup_missing_raises(registry: LibRegistry):
    with pytest.raises(LibNotFoundError):
        registry.lookup("ladle", "dispatcher", "missing")

def test_registry_namespace_mismatch_raises():
    reg = LibRegistry()
    agents_dir = os.path.join(FIXTURES, "agents_bad_namespace")
    with pytest.raises(LibRegistrationError):
        reg.scan(agents_dir)
```

Create `tests/fixtures/agents/ladle/libs/dispatcher.py`:

```python
from src.runtime.lib.decorator import lib_function

@lib_function(name="getCandidates", namespace="ladle", readonly=True)
def get_candidates(args: dict) -> dict:
    return {"candidates": []}
```

Create `tests/fixtures/agents_bad_namespace/converter/libs/planner.py`:

```python
from src.runtime.lib.decorator import lib_function

@lib_function(name="plan", namespace="wrong", readonly=True)
def plan(args: dict) -> dict:
    return {}
```

Add a pytest fixture in `tests/conftest.py` if it does not exist:

```python
import pytest
from src.runtime.lib.registry import LibRegistry

@pytest.fixture
def registry():
    reg = LibRegistry()
    yield reg
    reg.clear()
    LibRegistry.reset_instance()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/lib/registry.py
import importlib.util
import os
import sys
import threading
from pathlib import Path

from src.runtime.lib.decorator import lib_function
from src.runtime.lib.exceptions import LibNotFoundError, LibRegistrationError


class LibRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *, _singleton: bool = False):
        if _singleton:
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._init()
            return cls._instance
        return super().__new__(cls)

    def __init__(self, *, _singleton: bool = False):
        if not _singleton or getattr(self, "_registry", None) is None:
            self._init()

    def _init(self):
        self._registry = {}
        self._rlock = threading.RLock()
        self._agents_root: Path | None = None
        self._loaded_modules: set[str] = set()

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None

    @property
    def _data(self):
        return self._registry

    def clear(self):
        with self._rlock:
            self._registry.clear()
        for mod_name in list(self._loaded_modules):
            sys.modules.pop(mod_name, None)
        self._loaded_modules.clear()

    def scan(self, agents_root: str):
        agents_path = Path(agents_root)
        if not agents_path.exists():
            return
        self._agents_root = agents_path

        with self._rlock:
            self._registry.clear()
            for namespace_dir in agents_path.iterdir():
                if not namespace_dir.is_dir():
                    continue
                libs_dir = namespace_dir / "libs"
                if not libs_dir.exists():
                    continue
                namespace = namespace_dir.name
                for py_file in libs_dir.glob("*.py"):
                    self._load_module(namespace, py_file)

    def _exec_module(self, namespace: str, py_file: Path):
        module_name = f"_lib_registry_{namespace}_{py_file.stem}"
        if module_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        else:
            module = sys.modules[module_name]
            importlib.reload(module)
        self._loaded_modules.add(module_name)
        return module

    def _register_functions(self, namespace: str, py_file: Path, module):
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            meta = getattr(obj, "_lib_meta", None)
            if meta is None:
                continue
            declared_ns = meta["namespace"]
            if declared_ns != namespace:
                raise LibRegistrationError(
                    f"{py_file}",
                    details=f"namespace mismatch: declared '{declared_ns}' but file is under '{namespace}'"
                )
            key = f"{namespace}.{py_file.stem}.{meta['name']}"
            self._registry[key] = meta["func"]

    def _load_module(self, namespace: str, py_file: Path):
        module = self._exec_module(namespace, py_file)
        self._register_functions(namespace, py_file, module)

    def reload_module(self, py_file_path: str):
        py_file = Path(py_file_path)
        if self._agents_root is None:
            return
        try:
            rel = py_file.relative_to(self._agents_root)
        except ValueError:
            return
        parts = rel.parts
        if len(parts) < 3 or parts[1] != "libs":
            return
        namespace = parts[0]

        with self._rlock:
            module = self._exec_module(namespace, py_file)
            self._register_functions(namespace, py_file, module)

    def lookup(self, namespace: str, module: str, name: str):
        key = f"{namespace}.{module}.{name}"
        with self._rlock:
            func = self._registry.get(key)
        if func is None:
            raise LibNotFoundError(key, details="not registered")
        return func
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_registry.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/registry.py tests/runtime/lib/test_registry.py tests/fixtures tests/conftest.py
git commit -m "feat: add LibRegistry with scan and lookup"
```

---

### Task 4: `LibProxy` DSL object

**Files:**
- Create: `src/runtime/lib/proxy.py`
- Test: `tests/runtime/lib/test_proxy.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from src.runtime.lib.proxy import LibProxy
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError

def test_proxy_full_path(registry: LibRegistry):
    registry._data["ladle.dispatcher.getCandidates"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="ladle")
    result = proxy.ladle.dispatcher.getCandidates({})
    assert result == {"ok": True}

def test_proxy_omit_default_namespace(registry: LibRegistry):
    registry._data["ladle.dispatcher.getCandidates"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="ladle")
    result = proxy.dispatcher.getCandidates({})
    assert result == {"ok": True}

def test_proxy_shared_namespace(registry: LibRegistry):
    registry._data["shared.data_adapter.transform"] = lambda args: args
    proxy = LibProxy(default_namespace="ladle")
    result = proxy.shared.data_adapter.transform({"x": 1})
    assert result == {"x": 1}

def test_proxy_missing_raises():
    registry = LibRegistry()
    registry.clear()
    proxy = LibProxy(default_namespace="ladle")
    with pytest.raises(LibNotFoundError):
        proxy.missing.func({})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/lib/proxy.py
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError


class _LibProxyNode:
    def __init__(self, registry: LibRegistry, path: list[str], default_namespace: str | None):
        self._registry = registry
        self._path = path
        self._default_namespace = default_namespace

    def __getattr__(self, name: str):
        return _LibProxyNode(self._registry, self._path + [name], self._default_namespace)

    def __call__(self, *args, **kwargs):
        if len(self._path) < 2:
            raise LibNotFoundError(".".join(self._path), details="incomplete path")

        # Try default namespace omission
        candidates = []
        if self._default_namespace and len(self._path) == 2:
            # lib.module.name => default_namespace.module.name
            candidates.append(f"{self._default_namespace}.{self._path[0]}.{self._path[1]}")
        if len(self._path) >= 3:
            candidates.append(".".join(self._path))

        for key in candidates:
            func = self._registry._data.get(key)
            if func is not None:
                return func(*args, **kwargs)

        raise LibNotFoundError(".".join(self._path), details="not registered")


class LibProxy:
    def __init__(self, default_namespace: str | None = None, registry: LibRegistry | None = None):
        self._registry = registry or LibRegistry(_singleton=True)
        self._default_namespace = default_namespace

    def __getattr__(self, name: str):
        return _LibProxyNode(self._registry, [name], self._default_namespace)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_proxy.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/proxy.py tests/runtime/lib/test_proxy.py
git commit -m "feat: add LibProxy with namespace omission"
```

---

### Task 5: `SandboxExecutor`

**Files:**
- Create: `src/runtime/lib/sandbox.py`
- Test: `tests/runtime/lib/test_sandbox.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from src.runtime.lib.sandbox import SandboxExecutor, SAFE_BUILTINS
from src.runtime.lib.exceptions import ScriptExecutionError, ImmutableContextError

def test_sandbox_executes_simple_script():
    executor = SandboxExecutor()
    result = executor.execute("a = 1 + 2\nresult = a * 3", {"args": {"x": 1}})
    assert result == 9

def test_sandbox_can_import_whitelisted_module():
    executor = SandboxExecutor()
    result = executor.execute("import math\nresult = math.ceil(2.3)", {})
    assert result == 3

def test_sandbox_blocks_non_whitelisted_import():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("import os\nresult = 1", {})

def test_sandbox_blocks_open():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("open('foo.txt')", {})

def test_sandbox_blocks_eval():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("eval('1+1')", {})

def test_sandbox_blocks_compile():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("compile('1+1', '<string>', 'eval')", {})

def test_sandbox_blocks_getattr():
    executor = SandboxExecutor()
    with pytest.raises(ScriptExecutionError):
        executor.execute("getattr({}, 'keys')", {})

def test_safe_builtins_has_math():
    assert "abs" in SAFE_BUILTINS
    assert "open" not in SAFE_BUILTINS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_sandbox.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/runtime/lib/sandbox.py
import ast
import importlib
import traceback

from src.runtime.lib.exceptions import ScriptExecutionError, ImmutableContextError


SAFE_BUILTINS = frozenset({
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "chr", "complex", "dict", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max",
    "min", "next", "object", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "type", "vars", "zip",
    "Exception", "BaseException", "RuntimeError", "ValueError", "TypeError",
    "KeyError", "IndexError", "AttributeError", "StopIteration",
    "True", "False", "None",
})

FORBIDDEN_BUILTINS = frozenset({
    "open", "eval", "exec", "__import__", "compile",
    "getattr", "setattr", "delattr", "input", "breakpoint",
    "help", "quit", "exit",
})

PRELOADED_MODULES = {
    "math", "random", "statistics", "itertools", "functools",
    "operator", "collections", "json", "datetime", "time", "re",
    "string", "copy", "typing",
}


def _make_import_hook(allowed: set[str]):
    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        base = name.split(".")[0]
        if base not in allowed:
            raise ImportError(f"Import of '{name}' is not allowed in this sandbox")
        return __import__(name, globals, locals, fromlist, level)
    return _import


class SandboxExecutor:
    def execute(self, script: str, context: dict):
        try:
            tree = ast.parse(script, mode="exec")
        except SyntaxError as e:
            raise ScriptExecutionError(str(e), line=e.lineno)

        safe_builtins = {
            name: __builtins__[name]
            for name in SAFE_BUILTINS
            if name in __builtins__ and name not in FORBIDDEN_BUILTINS
        }
        safe_builtins["__import__"] = _make_import_hook(PRELOADED_MODULES)

        preloaded = {}
        for mod_name in PRELOADED_MODULES:
            try:
                preloaded[mod_name] = importlib.import_module(mod_name)
            except Exception:
                pass

        globals_dict = {"__builtins__": safe_builtins, **preloaded, **context}

        try:
            exec(compile(tree, "<sandbox>", "exec"), globals_dict)
        except Exception as e:
            if isinstance(e, ImmutableContextError):
                raise
            tb = e.__traceback__
            lineno = tb.tb_lineno if tb else None
            raise ScriptExecutionError(str(e), line=lineno) from e

        return globals_dict.get("result")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_sandbox.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/sandbox.py tests/runtime/lib/test_sandbox.py
git commit -m "feat: add SandboxExecutor with builtins whitelist"
```

---

### Task 6: `__init__.py` public exports

**Files:**
- Create: `src/runtime/lib/__init__.py`

- [ ] **Step 1: Write minimal implementation**

```python
from src.runtime.lib.decorator import lib_function
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.proxy import LibProxy
from src.runtime.lib.sandbox import SandboxExecutor, SAFE_BUILTINS
from src.runtime.lib.exceptions import (
    LibNotFoundError,
    LibExecutionError,
    LibRegistrationError,
    ScriptExecutionError,
    ImmutableContextError,
    LibValidationError,
)

__all__ = [
    "lib_function",
    "LibRegistry",
    "LibProxy",
    "SandboxExecutor",
    "SAFE_BUILTINS",
    "LibNotFoundError",
    "LibExecutionError",
    "LibRegistrationError",
    "ScriptExecutionError",
    "ImmutableContextError",
    "LibValidationError",
]
```

- [ ] **Step 2: Commit**

```bash
git add src/runtime/lib/__init__.py
git commit -m "feat: export public lib API"
```

---

### Task 7: Hot reload with `watchdog`

**Files:**
- Create: `src/runtime/lib/watcher.py`
- Test: `tests/runtime/lib/test_watcher.py`
- Modify: `pyproject.toml` or `requirements.txt`

- [ ] **Step 1: Write the failing test**

```python
import os
import time
import tempfile
import pytest
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.watcher import LibWatcher

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")

def test_watcher_detects_file_change():
    with tempfile.TemporaryDirectory() as tmpdir:
        ns_dir = os.path.join(tmpdir, "ladle", "libs")
        os.makedirs(ns_dir)
        py_path = os.path.join(ns_dir, "demo.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write('''
from src.runtime.lib.decorator import lib_function
@lib_function(name="demo", namespace="ladle", readonly=True)
def demo(args: dict) -> dict:
    return {"version": 1}
''')

        registry = LibRegistry()
        registry.clear()
        registry.scan(tmpdir)
        assert registry.lookup("ladle", "demo", "demo")({}) == {"version": 1}

        watcher = LibWatcher(tmpdir, registry=registry)
        watcher.start()

        # Modify file
        time.sleep(0.1)
        with open(py_path, "w", encoding="utf-8") as f:
            f.write('''
from src.runtime.lib.decorator import lib_function
@lib_function(name="demo", namespace="ladle", readonly=True)
def demo(args: dict) -> dict:
    return {"version": 2}
''')

        time.sleep(0.6)
        assert registry.lookup("ladle", "demo", "demo")({}) == {"version": 2}
        watcher.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_watcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

First, add `watchdog` to `requirements.txt`:

```
watchdog>=3.0.0
pytest>=7.0.0
```

Then implement `src/runtime/lib/watcher.py`:

```python
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.runtime.lib.registry import LibRegistry


class _ReloadHandler(FileSystemEventHandler):
    def __init__(self, registry: LibRegistry, agents_root: str):
        self.registry = registry
        self.agents_root = agents_root

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".py"):
            self.registry.reload_module(event.src_path)


class LibWatcher:
    def __init__(self, agents_root: str, registry: LibRegistry | None = None):
        self.agents_root = agents_root
        self.registry = registry or LibRegistry(_singleton=True)
        self.observer = Observer()
        self.handler = _ReloadHandler(self.registry, agents_root)

    def start(self):
        self.observer.schedule(self.handler, self.agents_root, recursive=True)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()
```

No additional registry changes needed — `reload_module` was already added in Task 3 using `importlib.reload()` and relative-path namespace derivation.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_watcher.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/lib/watcher.py tests/runtime/lib/test_watcher.py requirements.txt src/runtime/lib/registry.py
git commit -m "feat: add LibWatcher for hot reload"
```

---

### Task 8: End-to-end integration test

**Files:**
- Test: `tests/runtime/lib/test_integration.py`

- [ ] **Step 1: Write the failing test**

First create `tests/fixtures/agents/converter/libs/planner.py`:

```python
from src.runtime.lib.decorator import lib_function

@lib_function(name="plan", namespace="converter", readonly=True)
def plan(args: dict) -> dict:
    return {"plan": args["target"]}
```

Then write the test:

```python
import os
import pytest
from src.runtime.lib import (
    LibRegistry,
    LibProxy,
    SandboxExecutor,
    lib_function,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")

def test_full_dsl_run_script(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="ladle")

    script = """
result = lib.dispatcher.getCandidates({'converterId': args.converterId})
"""
    executor = SandboxExecutor()
    result = executor.execute(script, {
        "args": {"converterId": "C01"},
        "lib": proxy,
    })
    assert result == {"candidates": []}

def test_cross_namespace_call(registry: LibRegistry):
    registry.scan(os.path.join(FIXTURES, "agents"))
    proxy = LibProxy(default_namespace="ladle")

    script = "result = lib.converter.planner.plan({'target': 'A1'})"
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})
    assert result == {"plan": "A1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/lib/test_integration.py -v`
Expected: `ModuleNotFoundError` or test failure

- [ ] **Step 3: Write minimal implementation**

No new implementation needed — this step validates the integration of existing pieces. If tests fail, fix the underlying module.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/lib/test_integration.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/lib/test_integration.py tests/fixtures/agents/converter/libs/planner.py
git commit -m "test: end-to-end lib proxy + sandbox integration"
```

---

### Task 9: README / usage doc

**Files:**
- Create: `src/runtime/lib/README.md`

- [ ] **Step 1: Write minimal README**

```markdown
# runtime.lib

Agent Studio 脚本库运行时。

## Quick Start

```python
from runtime.lib import lib_function, LibRegistry, LibProxy, SandboxExecutor

@lib_function(name="hello", namespace="shared", readonly=True)
def hello(args: dict) -> dict:
    return {"msg": f"Hello, {args.get('name', 'world')}!"}

registry = LibRegistry()
registry.scan("agents/")

proxy = LibProxy(default_namespace="shared")
executor = SandboxExecutor()
result = executor.execute("result = lib.hello(args)", {"args": {"name": "Alice"}, "lib": proxy})
```

## Directory Layout

- `agents/<model>/libs/` → `lib.<model>.<module>.<function>`
- `agents/shared/libs/` → `lib.shared.<module>.<function>`
```

- [ ] **Step 2: Commit**

```bash
git add src/runtime/lib/README.md
git commit -m "docs: add runtime.lib usage readme"
```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-agent-studio-script-lib.md`.

**Next steps:**
1. Run the full test suite: `pytest tests/runtime/lib -v`
2. Ensure all tests pass before proceeding.
3. If any step fails, fix it in place and commit.
