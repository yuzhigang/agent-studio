# Project Runtime Isolation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the unified `agent-studio` CLI with cross-platform file locking, JSON-RPC runtime server, and an optional Supervisor gateway for managing runtime processes across local and edge deployments.

**Architecture:** The runtime uses `agent-studio run` for single-project process-level isolation, `agent-studio run-inline` for multi-project in-process development mode, and `agent-studio supervisor` as a management plane. A cross-platform `.lock` file prevents concurrent project access. Communication between Supervisor and runtimes uses WebSocket + JSON-RPC 2.0.

**Tech Stack:** Python 3.11+, `fasteners` (file locking), `websockets` (WebSocket server/client), `aiohttp` (Supervisor HTTP + WebSocket gateway), `pytest` (testing).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/runtime/locks/project_lock.py` | Cross-platform `.lock` file acquisition and release using `fasteners` |
| `src/runtime/project_registry.py` | Modified to acquire/release `.lock` during `load_project` / `unload_project` |
| `src/runtime/cli/main.py` | `agent-studio` CLI entry point with `run`, `run-inline`, `supervisor` subcommands |
| `src/runtime/cli/run_inline.py` | `agent-studio run-inline` implementation: load multiple projects in one process |
| `src/runtime/cli/run_command.py` | `agent-studio run` implementation: load project, start WebSocket server, connect Supervisor |
| `src/runtime/server/jsonrpc_ws.py` | Shared WebSocket JSON-RPC server handler for runtime |
| `src/runtime/server/supervisor_gateway.py` | Supervisor HTTP API + WebSocket gateway |
| `src/runtime/server/supervisor_client.py` | Optional client that connects `agent-studio run` back to Supervisor |
| `pyproject.toml` | Add `fasteners`, `websockets`, `aiohttp` dependencies and console script entry point |
| `tests/runtime/locks/test_project_lock.py` | Unit tests for file locking behavior |
| `tests/runtime/test_cli_run_inline.py` | Tests for run-inline loading and shutdown |
| `tests/runtime/test_cli_run_command.py` | Tests for `agent-studio run` start/stop logic |
| `tests/runtime/server/test_supervisor_gateway.py` | Tests for Supervisor routing and reverse registration |

---

## Phase 1: Cross-Platform File Lock + ProjectRegistry Integration

### Task 1: Add dependencies and console script

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies and CLI entry point**

Add `fasteners`, `websockets`, `aiohttp` to `[project.dependencies]` and register `agent-studio = "src.runtime.cli.main:main"` under `[project.scripts]`.

```toml
[project]
name = "agent-studio"
version = "0.1.0"
description = "Agent Studio"
requires-python = ">=3.11"
dependencies = [
    "watchdog>=3.0.0",
    "pyyaml>=6.0",
    "fasteners>=0.19",
    "websockets>=12.0",
    "aiohttp>=3.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
]

[project.scripts]
agent-studio = "src.runtime.cli.main:main"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "--import-mode=importlib"
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -e .`
Expected: installs successfully with no errors.

- [ ] **Step 3: Verify CLI is available**

Run: `agent-studio --help`
Expected: shows help output (placeholder if main.py not yet written, but command exists).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add fasteners, websockets, aiohttp and agent-studio CLI entry point"
```

### Task 2: Implement cross-platform project lock

**Files:**
- Create: `src/runtime/locks/__init__.py`
- Create: `src/runtime/locks/project_lock.py`
- Create: `tests/runtime/locks/test_project_lock.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/locks/test_project_lock.py
import os
import pytest
import tempfile
from src.runtime.locks.project_lock import ProjectLock, LockAlreadyHeldError


def test_acquire_and_release_lock():
    with tempfile.TemporaryDirectory() as tmp:
        lock = ProjectLock(tmp)
        lock.acquire()
        assert os.path.exists(os.path.join(tmp, ".lock"))
        lock.release()
        assert not os.path.exists(os.path.join(tmp, ".lock"))


def test_second_acquire_raises():
    with tempfile.TemporaryDirectory() as tmp:
        lock1 = ProjectLock(tmp)
        lock2 = ProjectLock(tmp)
        lock1.acquire()
        with pytest.raises(LockAlreadyHeldError):
            lock2.acquire()
        lock1.release()


def test_context_manager():
    with tempfile.TemporaryDirectory() as tmp:
        with ProjectLock(tmp) as lock:
            assert os.path.exists(os.path.join(tmp, ".lock"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/locks/test_project_lock.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.runtime.locks'" or import errors.

- [ ] **Step 3: Implement ProjectLock**

```python
# src/runtime/locks/__init__.py
from .project_lock import ProjectLock, LockAlreadyHeldError

__all__ = ["ProjectLock", "LockAlreadyHeldError"]
```

```python
# src/runtime/locks/project_lock.py
import os
import json
import fasteners


class LockAlreadyHeldError(RuntimeError):
    pass


class ProjectLock:
    def __init__(self, project_dir: str):
        self._project_dir = project_dir
        self._lock_path = os.path.join(project_dir, ".lock")
        self._lock = None
        self._acquired = False

    def acquire(self) -> None:
        os.makedirs(self._project_dir, exist_ok=True)
        self._lock = fasteners.InterProcessLock(self._lock_path)
        got_it = self._lock.acquire(blocking=False)
        if not got_it:
            pid = None
            if os.path.exists(self._lock_path):
                try:
                    with open(self._lock_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        pid = data.get("pid")
                except Exception:
                    pass
            project_id = os.path.basename(self._project_dir)
            if pid is not None:
                raise LockAlreadyHeldError(
                    f"Project {project_id} is already loaded in process {pid}"
                )
            raise LockAlreadyHeldError(f"Project {project_id} is already locked")
        self._acquired = True
        with open(self._lock_path, "w", encoding="utf-8") as f:
            json.dump(
                {"pid": os.getpid(), "started_at": _now_iso()}, f
            )

    def release(self) -> None:
        if self._acquired and self._lock is not None:
            try:
                if os.path.exists(self._lock_path):
                    os.remove(self._lock_path)
            except OSError:
                pass
            self._lock.release()
            self._acquired = False
            self._lock = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/locks/test_project_lock.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/runtime/locks/ tests/runtime/locks/
git commit -m "feat: add cross-platform ProjectLock with fasteners"
```

### Task 3: Integrate lock into ProjectRegistry

**Files:**
- Modify: `src/runtime/project_registry.py`
- Modify: `tests/runtime/test_project_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_project_registry.py`:

```python
import multiprocessing

from src.runtime.locks.project_lock import LockAlreadyHeldError


def _try_load_project_from_process(base_dir, project_id, result_queue):
    from src.runtime.project_registry import ProjectRegistry
    reg = ProjectRegistry(base_dir=base_dir)
    try:
        reg.load_project(project_id)
        result_queue.put("loaded")
    except Exception as e:
        result_queue.put(str(e))


def test_load_project_acquires_lock(registry):
    registry.create_project("proj-a")
    bundle = registry.load_project("proj-a")
    assert bundle["lock"] is not None


def test_double_load_same_process_returns_same_bundle(registry):
    registry.create_project("proj-a")
    bundle1 = registry.load_project("proj-a")
    bundle2 = registry.load_project("proj-a")
    assert bundle1 is bundle2


def test_concurrent_load_from_different_process_raises(registry):
    registry.create_project("proj-a")
    registry.load_project("proj-a")

    q = multiprocessing.Queue()
    p = multiprocessing.Process(
        target=_try_load_project_from_process, args=(registry._base_dir, "proj-a", q)
    )
    p.start()
    p.join()
    result = q.get()
    assert "already loaded" in result


def test_unload_project_releases_lock(registry):
    registry.create_project("proj-a")
    registry.load_project("proj-a")
    assert registry.unload_project("proj-a") is True
    # should be able to load again after unload
    bundle2 = registry.load_project("proj-a")
    assert bundle2 is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_project_registry.py::test_load_project_acquires_lock -v`
Expected: FAIL with AttributeError (no "lock" key in bundle).

- [ ] **Step 3: Modify ProjectRegistry**

Modify `src/runtime/project_registry.py`:

```python
import os
import yaml

from src.runtime.locks.project_lock import ProjectLock
from src.runtime.stores.sqlite_store import SQLiteStore
from src.runtime.event_bus import EventBusRegistry
from src.runtime.instance_manager import InstanceManager
from src.runtime.scene_manager import SceneManager
from src.runtime.state_manager import StateManager


class ProjectRegistry:
    def __init__(
        self,
        base_dir: str = "projects",
        metric_store_factory=None,
    ):
        self._base_dir = base_dir
        self._metric_store_factory = metric_store_factory
        self._loaded: dict[str, dict] = {}

    def _project_dir(self, project_id: str) -> str:
        return os.path.join(self._base_dir, project_id)

    def create_project(self, project_id: str, config: dict | None = None) -> dict:
        config = config or {}
        project_dir = self._project_dir(project_id)
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, "scenes"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "resources"), exist_ok=True)

        project_yaml = {
            "project_id": project_id,
            "name": config.get("name", project_id),
            "description": config.get("description", ""),
            "config": config,
        }
        yaml_path = os.path.join(project_dir, "project.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(project_yaml, f, allow_unicode=True, sort_keys=False)

        store = SQLiteStore(project_dir)
        store.save_project(project_id, config)
        store.close()

        return project_yaml

    def load_project(self, project_id: str) -> dict:
        if project_id in self._loaded:
            return self._loaded[project_id]

        project_dir = self._project_dir(project_id)
        if not os.path.isdir(project_dir):
            raise ValueError(f"Project {project_id} not found")

        yaml_path = os.path.join(project_dir, "project.yaml")
        if not os.path.exists(yaml_path):
            raise ValueError(f"Project {project_id} has no project.yaml")

        project_lock = ProjectLock(project_dir)
        project_lock.acquire()

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                project_yaml = yaml.safe_load(f)

            store = SQLiteStore(project_dir)
            store.save_project(project_id, project_yaml.get("config", {}))

            bus_reg = EventBusRegistry()
            im = InstanceManager(bus_reg, instance_store=store)
            scene_mgr = SceneManager(im, bus_reg, scene_store=store)
            metric_store = (
                self._metric_store_factory(project_id)
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

            state_mgr.restore_project(project_id)
            state_mgr.track_project(project_id)

            bundle = {
                "project_id": project_id,
                "project_yaml": project_yaml,
                "store": store,
                "event_bus_registry": bus_reg,
                "instance_manager": im,
                "scene_manager": scene_mgr,
                "state_manager": state_mgr,
                "metric_store": metric_store,
                "lock": project_lock,
                "_registry": self,
                "force_stop_on_shutdown": False,
            }
            self._loaded[project_id] = bundle
            return bundle
        except Exception:
            project_lock.release()
            raise

    def unload_project(self, project_id: str) -> bool:
        bundle = self._loaded.pop(project_id, None)
        if bundle is None:
            return False

        state_mgr = bundle["state_manager"]
        state_mgr.untrack_project(project_id)
        state_mgr.shutdown()

        store = bundle["store"]
        store.close()

        bus_reg = bundle["event_bus_registry"]
        bus_reg.destroy(project_id)

        project_lock = bundle["lock"]
        project_lock.release()

        return True

    def list_projects(self) -> list[str]:
        if not os.path.isdir(self._base_dir):
            return []
        return [
            name
            for name in os.listdir(self._base_dir)
            if os.path.isdir(os.path.join(self._base_dir, name))
            and os.path.exists(os.path.join(self._base_dir, name, "project.yaml"))
        ]

    def get_loaded_project(self, project_id: str) -> dict | None:
        return self._loaded.get(project_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/test_project_registry.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/runtime/project_registry.py tests/runtime/test_project_registry.py
git commit -m "feat: integrate ProjectLock into ProjectRegistry load/unload"
```

---

## Phase 2: CLI Scaffolding

### Task 4: Create CLI main entry point

**Files:**
- Create: `src/runtime/cli/__init__.py`
- Create: `src/runtime/cli/main.py`
- Create: `src/runtime/cli/run_inline.py`
- Create: `tests/runtime/test_cli_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/test_cli_main.py
import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "src.runtime.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "run-inline" in result.stdout
    assert "supervisor" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_cli_main.py -v`
Expected: FAIL with "No module named 'src.runtime.cli.main'" or similar.

- [ ] **Step 3: Implement CLI main and run-inline skeleton**

```python
# src/runtime/cli/__init__.py
```

```python
# src/runtime/cli/main.py
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-studio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run a single project in isolated process mode"
    )
    run_parser.add_argument(
        "--project-dir", required=True, help="Path to project directory"
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
        "run-inline", help="Run multiple projects in the current process"
    )
    inline_parser.add_argument(
        "--project-dir",
        action="append",
        required=True,
        help="Path to project directory (can be repeated)",
    )
    inline_parser.set_defaults(func=_run_inline_command)

    sup_parser = subparsers.add_parser(
        "supervisor", help="Start the Supervisor management plane"
    )
    sup_parser.add_argument(
        "--base-dir", default="projects", help="Base directory containing projects"
    )
    sup_parser.add_argument(
        "--ws-port", type=int, default=8001, help="WebSocket port for runtime registration"
    )
    sup_parser.add_argument(
        "--http-port", type=int, default=8080, help="HTTP port for management API"
    )
    sup_parser.set_defaults(func=_supervisor_command)

    args = parser.parse_args(argv)
    return args.func(args)


def _run_command(args):
    from src.runtime.cli.run_command import run_project
    return run_project(
        project_dir=args.project_dir,
        supervisor_ws=args.supervisor_ws,
        ws_port=args.ws_port,
        force_stop_on_shutdown=args.force_stop_on_shutdown,
    )


def _run_inline_command(args):
    from src.runtime.cli.run_inline import run_inline
    return run_inline(project_dirs=args.project_dir)


def _supervisor_command(args):
    from src.runtime.cli.supervisor_command import run_supervisor
    return run_supervisor(
        base_dir=args.base_dir,
        ws_port=args.ws_port,
        http_port=args.http_port,
    )


if __name__ == "__main__":
    sys.exit(main())
```

```python
# src/runtime/cli/run_inline.py
import os
import signal
import sys

from src.runtime.project_registry import ProjectRegistry


def run_inline(project_dirs):
    registries = _load_projects(project_dirs)

    def _shutdown(signum, frame):
        print("Shutting down inline runtime...")
        for registry in registries:
            for project_id in list(registry._loaded.keys()):
                registry.unload_project(project_id)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import threading
    threading.Event().wait()
    return 0


def _load_projects(project_dirs):
    registries = []
    for project_dir in project_dirs:
        base_dir = os.path.dirname(os.path.abspath(project_dir))
        project_id = os.path.basename(os.path.abspath(project_dir))
        registry = ProjectRegistry(base_dir=base_dir)
        registry.load_project(project_id)
        registries.append(registry)
    return registries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_cli_main.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/runtime/cli/ tests/runtime/test_cli_main.py
git commit -m "feat: add agent-studio CLI entry with run, run-inline, supervisor commands"
```

### Task 5: Test run-inline loading and shutdown

**Files:**
- Create: `tests/runtime/test_cli_run_inline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/test_cli_run_inline.py
import os
import tempfile
from src.runtime.project_registry import ProjectRegistry
from src.runtime.cli.run_inline import _load_projects


def test_load_projects_inline():
    with tempfile.TemporaryDirectory() as tmp:
        reg1 = ProjectRegistry(base_dir=tmp)
        reg1.create_project("factory-01")
        reg2 = ProjectRegistry(base_dir=tmp)
        reg2.create_project("factory-02")
        dirs = [os.path.join(tmp, "factory-01"), os.path.join(tmp, "factory-02")]
        registries = _load_projects(dirs)
        assert registries[0].get_loaded_project("factory-01") is not None
        assert registries[1].get_loaded_project("factory-02") is not None
        for r in registries:
            for pid in list(r._loaded.keys()):
                r.unload_project(pid)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_cli_run_inline.py -v`
Expected: FAIL with import error or assertion error.

- [ ] **Step 3: Ensure implementation exists**

`src/runtime/cli/run_inline.py` already written in Task 4. If test fails for a real bug, fix it.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_cli_run_inline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_cli_run_inline.py
git commit -m "test: add run-inline loading tests"
```

---

## Phase 3: `agent-studio run` Runtime Process

### Task 6: JSON-RPC WebSocket server utilities

**Files:**
- Create: `src/runtime/server/__init__.py`
- Create: `src/runtime/server/jsonrpc_ws.py`
- Create: `tests/runtime/server/test_jsonrpc_ws.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/server/test_jsonrpc_ws.py
import pytest
import asyncio
from src.runtime.server.jsonrpc_ws import JsonRpcConnection


def test_parse_request():
    conn = JsonRpcConnection(None)
    req = conn.parse_message('{"jsonrpc": "2.0", "id": 1, "method": "hello", "params": {"a": 1}}')
    assert req["method"] == "hello"
    assert req["id"] == 1


def test_build_response():
    conn = JsonRpcConnection(None)
    resp = conn.build_response(1, {"status": "ok"})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["status"] == "ok"


def test_build_error():
    conn = JsonRpcConnection(None)
    resp = conn.build_error(1, -32001, "locked")
    assert resp["error"]["code"] == -32001
    assert resp["error"]["message"] == "locked"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/server/test_jsonrpc_ws.py -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Implement JsonRpcConnection**

```python
# src/runtime/server/__init__.py
from .jsonrpc_ws import JsonRpcConnection

__all__ = ["JsonRpcConnection"]
```

```python
# src/runtime/server/jsonrpc_ws.py
import json
import asyncio


class JsonRpcConnection:
    def __init__(self, websocket):
        self._ws = websocket
        self._handlers = {}

    def register(self, method: str, handler):
        self._handlers[method] = handler

    def parse_message(self, raw: str) -> dict:
        return json.loads(raw)

    def build_response(self, req_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def build_error(self, req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def build_notification(self, method: str, params: dict) -> dict:
        return {"jsonrpc": "2.0", "method": method, "params": params}

    async def handle_message(self, raw: str) -> dict | None:
        msg = self.parse_message(raw)
        if "method" not in msg:
            return None
        method = msg["method"]
        req_id = msg.get("id")
        params = msg.get("params", {})
        handler = self._handlers.get(method)
        if handler is None:
            if req_id is not None:
                return self.build_error(req_id, -32601, f"Method not found: {method}")
            return None
        try:
            result = await handler(params, req_id)
            if req_id is not None and result is not None:
                return self.build_response(req_id, result)
        except JsonRpcError as e:
            if req_id is not None:
                return self.build_error(req_id, e.code, e.message)
        except Exception as e:
            if req_id is not None:
                return self.build_error(req_id, -32603, str(e))
        return None

    async def send(self, msg: dict):
        if self._ws is not None and not self._ws.closed:
            await self._ws.send(json.dumps(msg))

    async def close(self):
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/server/test_jsonrpc_ws.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/runtime/server/ tests/runtime/server/
git commit -m "feat: add JsonRpcConnection utilities"
```

### Task 7: Implement `agent-studio run` command

**Files:**
- Create: `src/runtime/cli/run_command.py`
- Create: `tests/runtime/test_cli_run_command.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/test_cli_run_command.py
import os
import tempfile
import threading
import time
from src.runtime.project_registry import ProjectRegistry
from src.runtime.cli.run_command import _start_shared_scenes, _graceful_shutdown


def test_start_shared_scenes_restores_shared():
    with tempfile.TemporaryDirectory() as tmp:
        reg = ProjectRegistry(base_dir=tmp)
        reg.create_project("proj-a")
        bundle = reg.load_project("proj-a")
        sm = bundle["scene_manager"]
        store = bundle["store"]
        # create a shared scene via scene manager and persist it
        sm.start("proj-a", "scene-1", mode="shared")
        sm.checkpoint_scene("proj-a", "scene-1")
        reg.unload_project("proj-a")

        # reload and auto-start shared scenes
        bundle2 = reg.load_project("proj-a")
        _start_shared_scenes(bundle2)
        assert bundle2["scene_manager"].get("proj-a", "scene-1") is not None
        reg.unload_project("proj-a")


def test_graceful_shutdown_unloads_and_releases_lock():
    with tempfile.TemporaryDirectory() as tmp:
        reg = ProjectRegistry(base_dir=tmp)
        reg.create_project("proj-a")
        bundle = reg.load_project("proj-a")
        _graceful_shutdown(bundle, force_stop_on_shutdown=False)
        assert reg.get_loaded_project("proj-a") is None
        # lock should be released, so reload works
        bundle2 = reg.load_project("proj-a")
        assert bundle2 is not None
        reg.unload_project("proj-a")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_cli_run_command.py -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Implement run_command**

```python
# src/runtime/cli/run_command.py
import asyncio
import json
import os
import signal
import sys
import threading
import uuid

from src.runtime.project_registry import ProjectRegistry
from src.runtime.server.jsonrpc_ws import JsonRpcConnection, JsonRpcError


def run_project(project_dir, supervisor_ws=None, ws_port=None, force_stop_on_shutdown=None):
    base_dir = os.path.dirname(os.path.abspath(project_dir))
    project_id = os.path.basename(os.path.abspath(project_dir))

    registry = ProjectRegistry(base_dir=base_dir)
    bundle = registry.load_project(project_id)

    # Apply CLI override or default
    if force_stop_on_shutdown is None:
        force_stop_on_shutdown = False

    _start_shared_scenes(bundle)

    # Setup signal handlers for graceful shutdown
    def _on_signal(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        try:
            _graceful_shutdown(bundle)
        except JsonRpcError as e:
            # Per spec: SIGTERM with blocked shutdown should log and return without exiting
            print(f"Shutdown aborted: {e.message}")
            return
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    tasks = []

    if ws_port is not None:
        tasks.append(loop.create_task(_run_ws_server(bundle, ws_port)))

    if supervisor_ws is not None:
        tasks.append(loop.create_task(_run_supervisor_client(bundle, supervisor_ws)))

    try:
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks))
        else:
            # Block forever if no async tasks
            loop.run_until_complete(_block_forever())
    finally:
        loop.close()

    return 0


def _start_shared_scenes(bundle):
    store = bundle["store"]
    sm = bundle["scene_manager"]
    project_id = bundle["project_id"]
    scenes = store.list_scenes(project_id)
    for scene_data in scenes:
        if scene_data.get("mode") == "shared":
            scene_id = scene_data["scene_id"]
            refs = scene_data.get("refs", [])
            local_instances = scene_data.get("local_instances", {})
            sm.start(project_id, scene_id, mode="shared", references=refs, local_instances=local_instances)


def _graceful_shutdown(bundle, force_stop_on_shutdown=None):
    project_id = bundle["project_id"]
    sm = bundle["scene_manager"]
    state_mgr = bundle["state_manager"]
    registry = bundle.get("_registry")

    if force_stop_on_shutdown is None:
        force_stop_on_shutdown = bundle.get("force_stop_on_shutdown", False)

    # 1. Stop isolated scenes
    isolated_scenes = [s for s in sm.list_by_project(project_id) if s.get("mode") == "isolated"]
    for scene in isolated_scenes:
        if not force_stop_on_shutdown:
            raise JsonRpcError(-32003, "isolated scenes are running and force_stop_on_shutdown is false")
        sm.stop(project_id, scene["scene_id"])

    # 2. Stop shared scenes
    shared_scenes = [s for s in sm.list_by_project(project_id) if s.get("mode") == "shared"]
    for scene in shared_scenes:
        sm.stop(project_id, scene["scene_id"])

    # 3. Untrack and checkpoint
    state_mgr.untrack_project(project_id)
    lock = state_mgr._get_project_lock(project_id)
    with lock:
        state_mgr.checkpoint_project(project_id)

    # 4. Unload project and release file lock
    if registry is not None:
        registry.unload_project(project_id)


async def _block_forever():
    await asyncio.Event().wait()


async def _run_ws_server(bundle, port):
    import websockets

    async def handler(websocket, path):
        conn = JsonRpcConnection(websocket)
        _register_runtime_handlers(conn, bundle)
        try:
            async for message in websocket:
                resp = await conn.handle_message(message)
                if resp is not None:
                    await conn.send(resp)
        except websockets.exceptions.ConnectionClosed:
            pass

    start_server = websockets.serve(handler, "0.0.0.0", port)
    server = await start_server
    try:
        await asyncio.Future()  # run forever
    finally:
        server.close()
        await server.wait_closed()


async def _run_supervisor_client(bundle, supervisor_ws):
    import websockets

    session_id = str(uuid.uuid4())
    project_id = bundle["project_id"]
    disconnected_at = None

    while True:
        try:
            async with websockets.connect(supervisor_ws) as ws:
                disconnected_at = None
                conn = JsonRpcConnection(ws)
                # Send runtimeOnline
                await conn.send(
                    conn.build_notification(
                        "notify.runtimeOnline",
                        {"project_id": project_id, "session_id": session_id},
                    )
                )

                # Heartbeat loop
                while True:
                    await asyncio.sleep(5)
                    if ws.closed:
                        break
                    await conn.send(
                        conn.build_notification(
                            "notify.heartbeat",
                            {"project_id": project_id, "session_id": session_id},
                        )
                    )
        except (websockets.exceptions.ConnectionClosed, OSError):
            pass

        # Track disconnect time; if > 15s, self-terminate to avoid concurrent runtime
        now = asyncio.get_event_loop().time()
        if disconnected_at is None:
            disconnected_at = now
        elif now - disconnected_at > 15:
            print("Supervisor unreachable for 15s, initiating self-termination...")
            _graceful_shutdown(bundle)
            break

        await asyncio.sleep(5)


def _register_runtime_handlers(conn: JsonRpcConnection, bundle: dict):
    project_id = bundle["project_id"]
    sm = bundle["scene_manager"]
    state_mgr = bundle["state_manager"]

    async def project_stop(params, req_id):
        _graceful_shutdown(bundle)
        return {"status": "stopped"}

    async def project_checkpoint(params, req_id):
        lock = state_mgr._get_project_lock(project_id)
        with lock:
            state_mgr.checkpoint_project(project_id)
        return {"status": "checkpointed"}

    async def project_get_status(params, req_id):
        return {
            "project_id": project_id,
            "loaded": True,
            "scenes": [s["scene_id"] for s in sm.list_by_project(project_id)],
        }

    async def scene_start(params, req_id):
        scene_id = params.get("scene_id")
        if scene_id is None:
            raise JsonRpcError(-32602, "scene_id required")
        existing = sm.get(project_id, scene_id)
        if existing is not None:
            return {"status": "already_running"}
        sm.start(project_id, scene_id, mode="isolated")
        return {"status": "started"}

    async def scene_stop(params, req_id):
        scene_id = params.get("scene_id")
        if scene_id is None:
            raise JsonRpcError(-32602, "scene_id required")
        ok = sm.stop(project_id, scene_id)
        if not ok:
            raise JsonRpcError(-32002, "scene not found")
        return {"status": "stopped"}

    conn.register("project.stop", project_stop)
    conn.register("project.checkpoint", project_checkpoint)
    conn.register("project.getStatus", project_get_status)
    conn.register("scene.start", scene_start)
    conn.register("scene.stop", scene_stop)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/test_cli_run_command.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/runtime/cli/run_command.py tests/runtime/test_cli_run_command.py
git commit -m "feat: implement agent-studio run with WebSocket and Supervisor client"
```

---

## Phase 4: Supervisor Gateway

### Task 8: Implement Supervisor HTTP + WebSocket gateway

**Files:**
- Create: `src/runtime/cli/supervisor_command.py`
- Create: `src/runtime/server/supervisor_gateway.py`
- Create: `tests/runtime/server/test_supervisor_gateway.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/server/test_supervisor_gateway.py
import pytest
import asyncio
from aiohttp import web
from src.runtime.server.supervisor_gateway import SupervisorGateway


@pytest.fixture
def gateway():
    return SupervisorGateway(base_dir="projects")


def test_register_runtime(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
        async def send(self, msg):
            pass
        async def close(self):
            self.closed = True

    ws = FakeWs()
    gateway.register_runtime("proj-a", ws, "sess-1")
    assert gateway.get_runtime("proj-a") == (ws, "sess-1")


def test_replace_runtime_session(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
            self.sent = []
        async def send(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws1 = FakeWs()
    ws2 = FakeWs()
    gateway.register_runtime("proj-a", ws1, "sess-1")
    gateway.register_runtime("proj-a", ws2, "sess-2")
    assert ws1.closed is True
    assert gateway.get_runtime("proj-a") == (ws2, "sess-2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/server/test_supervisor_gateway.py -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Implement SupervisorGateway and command**

```python
# src/runtime/server/supervisor_gateway.py
import json
import asyncio


class SupervisorGateway:
    def __init__(self, base_dir: str = "projects"):
        self._base_dir = base_dir
        self._runtimes: dict[str, tuple] = {}  # project_id -> (ws, session_id)
        self._lock = asyncio.Lock()
        self._clients: list = []  # list of client websockets

    async def register_runtime(self, project_id: str, ws, session_id: str):
        async with self._lock:
            old = self._runtimes.pop(project_id, None)
            if old is not None:
                old_ws, _ = old
                try:
                    await old_ws.close()
                except Exception:
                    pass
            self._runtimes[project_id] = (ws, session_id)
            await self._broadcast(
                {"jsonrpc": "2.0", "method": "notify.sessionReset", "params": {"project_id": project_id}}
            )

    async def unregister_runtime(self, project_id: str):
        async with self._lock:
            self._runtimes.pop(project_id, None)

    def get_runtime(self, project_id: str) -> tuple | None:
        return self._runtimes.get(project_id)

    async def send_to_runtime(self, project_id: str, message: dict) -> bool:
        runtime = self.get_runtime(project_id)
        if runtime is None:
            return False
        ws, _ = runtime
        try:
            await ws.send_str(json.dumps(message))
            return True
        except Exception:
            return False

    async def add_client(self, ws):
        self._clients.append(ws)

    async def remove_client(self, ws):
        if ws in self._clients:
            self._clients.remove(ws)

    async def _broadcast(self, message: dict):
        dead = []
        for ws in self._clients:
            try:
                await ws.send_str(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.remove_client(ws)
```

```python
# src/runtime/cli/supervisor_command.py
import asyncio
import json
import subprocess
import sys

from aiohttp import web
from src.runtime.server.supervisor_gateway import SupervisorGateway


def run_supervisor(base_dir="projects", ws_port=8001, http_port=8080):
    gateway = SupervisorGateway(base_dir=base_dir)
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = ws_port
    app["http_port"] = http_port

    app.router.add_post("/api/projects/{project_id}/start", _handle_start)
    app.router.add_post("/api/projects/{project_id}/stop", _handle_stop)
    app.router.add_get("/workers", _handle_worker_ws)
    app.router.add_get("/ws", _handle_client_ws)

    web.run_app(app, host="0.0.0.0", port=http_port)
    return 0


async def _handle_start(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    ws_port = request.app["ws_port"]
    http_port = request.app["http_port"]
    project_id = request.match_info["project_id"]
    runtime = gateway.get_runtime(project_id)
    if runtime is not None:
        return web.json_response({"status": "already_running"})

    # Spawn local subprocess
    project_dir = f"{gateway._base_dir}/{project_id}"
    supervisor_ws = f"ws://localhost:{ws_port}/workers"
    cmd = [
        sys.executable,
        "-m",
        "src.runtime.cli.main",
        "run",
        f"--project-dir={project_dir}",
        f"--supervisor-ws={supervisor_ws}",
    ]
    subprocess.Popen(cmd)
    return web.json_response({"status": "starting"})


async def _handle_stop(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    project_id = request.match_info["project_id"]
    runtime = gateway.get_runtime(project_id)
    if runtime is None:
        return web.json_response({"error": "not_running"}, status=404)

    ok = await gateway.send_to_runtime(
        project_id,
        {"jsonrpc": "2.0", "id": 1, "method": "project.stop", "params": {}},
    )
    if not ok:
        return web.json_response({"error": "send_failed"}, status=502)
    return web.json_response({"status": "stop_requested"})


async def _handle_worker_ws(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    session_id = None
    project_id = None

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            method = data.get("method")
            params = data.get("params", {})
            if method == "notify.runtimeOnline":
                project_id = params.get("project_id")
                session_id = params.get("session_id")
                if project_id and session_id:
                    await gateway.register_runtime(project_id, ws, session_id)
            elif method == "notify.runtimeOffline":
                if project_id:
                    await gateway.unregister_runtime(project_id)
        elif msg.type == web.WSMsgType.ERROR:
            break

    if project_id:
        await gateway.unregister_runtime(project_id)
    return ws


async def _handle_client_ws(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await gateway.add_client(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                # Forward client messages to runtime if routed
                data = json.loads(msg.data)
                project_id = data.get("params", {}).get("project_id")
                if project_id:
                    await gateway.send_to_runtime(project_id, data)
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        await gateway.remove_client(ws)
    return ws
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/runtime/server/test_supervisor_gateway.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/runtime/cli/supervisor_command.py src/runtime/server/supervisor_gateway.py tests/runtime/server/test_supervisor_gateway.py
git commit -m "feat: add Supervisor gateway with HTTP API and WebSocket routing"
```

---

## Phase 5: Integration

### Task 9: End-to-end smoke test for local spawn flow

**Files:**
- Create: `tests/runtime/test_e2e_local_spawn.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/test_e2e_local_spawn.py
import os
import tempfile
import time
import subprocess
import sys
import pytest


@pytest.mark.skip(reason="run manually or after full stack is stable")
def test_local_spawn_via_supervisor():
    """Manual/integration test: start supervisor, spawn a runtime, stop it."""
    pass
```

- [ ] **Step 2: Run test to verify it is skipped**

Run: `pytest tests/runtime/test_e2e_local_spawn.py -v`
Expected: 1 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/runtime/test_e2e_local_spawn.py
git commit -m "test: add e2e local spawn smoke test placeholder"
```

### Task 10: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/runtime/ -v`
Expected: All tests pass.

- [ ] **Step 2: Commit any fixes**

If any tests fail, fix and commit.

---

## Design Notes for Implementers

### `run_project` graceful shutdown details

When `project.stop` RPC is received or SIGTERM is caught:
1. Check isolated scenes. If any exist and `force_stop_on_shutdown` is `False`, abort shutdown with JSON-RPC error `-32003`.
2. Stop all shared scenes via `SceneManager.stop()`.
3. Untrack project from `StateManager` to disable auto-checkpoint.
4. Acquire per-project memory lock and run final `checkpoint_project()`.
5. Call `ProjectRegistry.unload_project()` which closes store, destroys event bus, and releases file lock.

### Supervisor spawn assumptions

`_handle_start` assumes the `agent-studio` CLI is available in `PATH` (via the pip-editable install). It spawns:
```bash
python -m src.runtime.cli.main run --project-dir=projects/{id} --supervisor-ws=ws://localhost:{ws_port}/workers
```

### WebSocket disconnect behavior

The supervisor client in `run_command.py` tracks the time since the last successful connection. If the connection remains down for more than 15 seconds, it triggers graceful shutdown and exits to prevent stale runtimes from competing with a replacement.

### Error codes

| Code | Meaning |
|---|---|
| `-32001` | Project already locked by another runtime |
| `-32002` | Scene not found |
| `-32003` | Illegal lifecycle transition (e.g., shutdown blocked by isolated scenes) |
| `-32004` | Project not loaded |
| `-32601` | JSON-RPC method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |

