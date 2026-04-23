# Worker-Supervisor Registration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Worker-Supervisor registration from world-level to worker-level, enable bidirectional command communication, and unify run/run-inline communication paths.

**Architecture:** Introduce `WorkerManager` as the central coordinator in each Worker process. Refactor `WorkerController` to manage `WorkerState` objects with dual-index lookup. All commands route through `WorkerManager` which delegates to per-world bundles.

**Tech Stack:** Python, asyncio, WebSocket (websockets/aiohttp), JSON-RPC 2.0, pytest, anyio

**Spec:** [docs/superpowers/specs/2026-04-22-worker-supervisor-registration-design.md](../specs/2026-04-22-worker-supervisor-registration-design.md)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/worker/manager.py` | Create | `WorkerManager`: manages `world_id -> bundle` mapping, handles Supervisor commands, sends heartbeats |
| `src/supervisor/gateway.py` | Modify | `WorkerController`: refactored from world-level to worker-level, with `_workers` and `_world_to_worker` indexes |
| `src/supervisor/server.py` | Modify | WebSocket handler for `/workers`: processes `notify.worker.activated` / `heartbeat` / `deactivated` |
| `src/worker/cli/run_command.py` | Modify | `run_world`: loads all worlds from base_dir, uses `WorkerManager`, registers command handlers on WebSocket connection |
| `src/worker/cli/run_inline.py` | Modify | `run_inline`: uses `WorkerManager`, connects via WebSocket loopback |
| `tests/worker/test_manager.py` | Create | Unit tests for `WorkerManager` |
| `tests/supervisor/test_gateway.py` | Modify | Update tests for new `WorkerState`-based API |
| `tests/worker/cli/test_run_command.py` | Modify | Update tests for multi-world loading |
| `tests/worker/cli/test_run_inline.py` | Modify | Update tests for `WorkerManager` integration |

---

## Task 1: WorkerManager

**Files:**
- Create: `src/worker/manager.py`
- Test: `tests/worker/test_manager.py`

`WorkerManager` is the central hub inside each Worker process. It:
- Loads all worlds from a base directory via `WorldRegistry`
- Maintains `world_id -> bundle` mapping
- Handles Supervisor commands (`world.stop`, `scene.start`, etc.)
- Sends `notify.worker.activated` and periodic `notify.worker.heartbeat`

### Step 1: Write failing test for WorkerManager creation

```python
import pytest
from src.worker.manager import WorkerManager


def test_worker_manager_init():
    wm = WorkerManager(worker_id="wk-1")
    assert wm.worker_id == "wk-1"
    assert wm.session_id is not None
    assert wm.worlds == {}
```

**Run:** `pytest tests/worker/test_manager.py::test_worker_manager_init -v`
**Expected:** FAIL (WorkerManager not found)

### Step 2: Implement WorkerManager skeleton

```python
import asyncio
import uuid
from datetime import datetime


class WorkerManager:
    def __init__(self, worker_id: str | None = None):
        self.worker_id = worker_id or str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.worlds: dict[str, dict] = {}  # world_id -> bundle
        self._heartbeat_task: asyncio.Task | None = None
```

**Run:** `pytest tests/worker/test_manager.py::test_worker_manager_init -v`
**Expected:** PASS

### Step 3: Write failing test for load_worlds

```python
def test_worker_manager_load_worlds():
    import tempfile
    from src.runtime.world_registry import WorldRegistry

    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")
        reg.create_world("factory-02")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        assert "factory-01" in wm.worlds
        assert "factory-02" in wm.worlds

        # Cleanup
        for wid in list(wm.worlds.keys()):
            wm.unload_world(wid)
```

**Run:** `pytest tests/worker/test_manager.py::test_worker_manager_load_worlds -v`
**Expected:** FAIL (load_worlds not defined)

### Step 4: Implement load_worlds and unload_world

```python
def load_worlds(self, base_dir: str) -> list[str]:
    from src.runtime.world_registry import WorldRegistry

    registry = WorldRegistry(base_dir=base_dir)
    world_ids = registry.list_worlds()
    for world_id in world_ids:
        bundle = registry.load_world(world_id)
        self.worlds[world_id] = bundle
    return world_ids


def unload_world(self, world_id: str) -> bool:
    bundle = self.worlds.pop(world_id, None)
    if bundle is None:
        return False
    state_mgr = bundle["state_manager"]
    state_mgr.untrack_world(world_id)
    state_mgr.checkpoint_world(world_id)
    store = bundle["store"]
    store.close()
    bus_reg = bundle["event_bus_registry"]
    bus_reg.destroy(world_id)
    world_lock = bundle["lock"]
    world_lock.release()
    return True
```

**Run:** `pytest tests/worker/test_manager.py::test_worker_manager_load_worlds -v`
**Expected:** PASS

### Step 5: Write failing test for handle_command

```python
def test_worker_manager_handle_command_world_stop():
    import tempfile
    from src.runtime.world_registry import WorldRegistry

    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("factory-01")

        wm = WorkerManager(worker_id="wk-1")
        wm.load_worlds(tmp)

        result = wm.handle_command("world.stop", {"world_id": "factory-01"})
        assert result["status"] == "stopped"
        assert "factory-01" not in wm.worlds
```

**Run:** `pytest tests/worker/test_manager.py::test_worker_manager_handle_command_world_stop -v`
**Expected:** FAIL (handle_command not defined)

### Step 6: Implement handle_command with all commands

```python
def handle_command(self, method: str, params: dict) -> dict:
    from src.worker.server.jsonrpc_ws import JsonRpcError

    world_id = params.get("world_id")
    bundle = self.worlds.get(world_id) if world_id else None

    if method == "world.stop":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        force = params.get("force_stop_on_shutdown")
        self._graceful_shutdown(bundle, force_stop_on_shutdown=force)
        self.worlds.pop(world_id, None)
        return {"status": "stopped"}

    if method == "world.checkpoint":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        bundle["state_manager"].checkpoint_world(world_id)
        return {"status": "checkpointed"}

    if method == "world.getStatus":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        return {
            "world_id": world_id,
            "loaded": True,
            "scenes": [s["scene_id"] for s in bundle["scene_manager"].list_by_world(world_id)],
        }

    if method == "world.start":
        from src.runtime.world_registry import WorldRegistry
        world_dir = params.get("world_dir")
        if world_dir is None:
            raise JsonRpcError(-32602, "world_dir required for world.start")
        base_dir = os.path.dirname(os.path.abspath(world_dir))
        registry = WorldRegistry(base_dir=base_dir)
        new_bundle = registry.load_world(world_id)
        self.worlds[world_id] = new_bundle
        return {"status": "started"}

    if method == "world.reload":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        # TODO: implement hot reload in follow-up task
        raise JsonRpcError(-32601, "world.reload not yet implemented")

    if method == "scene.start":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        scene_id = params.get("scene_id")
        if scene_id is None:
            raise JsonRpcError(-32602, "scene_id required")
        existing = bundle["scene_manager"].get(world_id, scene_id)
        if existing is not None:
            return {"status": "already_running"}
        bundle["scene_manager"].start(world_id, scene_id, mode="isolated")
        return {"status": "started"}

    if method == "scene.stop":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        scene_id = params.get("scene_id")
        if scene_id is None:
            raise JsonRpcError(-32602, "scene_id required")
        ok = bundle["scene_manager"].stop(world_id, scene_id)
        if not ok:
            raise JsonRpcError(-32002, "scene not found")
        return {"status": "stopped"}

    if method == "messageHub.publish":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        hub = bundle.get("message_hub")
        if hub is None:
            raise JsonRpcError(-32102, "message hub not initialized")
        hub.on_channel_message(
            params.get("event_type", ""),
            params.get("payload", {}),
            params.get("source", ""),
            params.get("scope", "world"),
            params.get("target"),
        )
        return {"acked": True}

    if method == "messageHub.publishBatch":
        if bundle is None:
            raise JsonRpcError(-32004, f"World {world_id} not loaded")
        hub = bundle.get("message_hub")
        if hub is None:
            raise JsonRpcError(-32102, "message hub not initialized")
        records = params.get("records", [])
        for record in records:
            hub.on_channel_message(
                record.get("event_type", ""),
                record.get("payload", {}),
                record.get("source", ""),
                record.get("scope", "world"),
                record.get("target"),
            )
        return {"acked_ids": [r.get("id") for r in records]}

    raise JsonRpcError(-32601, f"Unknown method: {method}")
```

Also add `_graceful_shutdown` helper (adapted from `run_command.py`):

```python
def _graceful_shutdown(self, bundle: dict, force_stop_on_shutdown: bool | None = None) -> None:
    world_id = bundle["world_id"]
    sm = bundle["scene_manager"]
    state_mgr = bundle["state_manager"]
    registry = bundle.get("_registry")

    if force_stop_on_shutdown is None:
        force_stop_on_shutdown = bundle.get("force_stop_on_shutdown", False)

    # 1. Stop isolated scenes (respect force_stop_on_shutdown)
    isolated_scenes = [s for s in sm.list_by_world(world_id) if s.get("mode") == "isolated"]
    for scene in isolated_scenes:
        if not force_stop_on_shutdown:
            from src.worker.server.jsonrpc_ws import JsonRpcError
            raise JsonRpcError(-32003, "isolated scenes are running and force_stop_on_shutdown is false")
        sm.stop(world_id, scene["scene_id"])

    # 2. Stop shared scenes
    for scene in sm.list_by_world(world_id):
        if scene.get("mode") == "shared":
            sm.stop(world_id, scene["scene_id"])

    # 3. Untrack and checkpoint
    state_mgr.untrack_world(world_id)
    state_mgr.checkpoint_world(world_id)

    # 4. Unload world and release file lock
    if registry is not None:
        registry.unload_world(world_id)
```

**Run:** `pytest tests/worker/test_manager.py -v`
**Expected:** PASS

### Step 7: Commit

```bash
rtk git add src/worker/manager.py tests/worker/test_manager.py
rtk git commit -m "feat: add WorkerManager for centralized world bundle management"
```

---

## Task 2: Supervisor Gateway Refactor

**Files:**
- Modify: `src/supervisor/gateway.py`
- Test: `tests/supervisor/test_gateway.py`

### Step 1: Write failing test for WorkerState-based registration

```python
import pytest
import asyncio
from src.supervisor.gateway import WorkerController, WorkerState


@pytest.fixture
def gateway():
    return WorkerController(base_dir="worlds")


def test_register_worker(gateway):
    class FakeWs:
        def __init__(self):
            self.closed = False
            self.sent = []
        async def send_str(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws = FakeWs()
    asyncio.run(gateway.register_worker("wk-1", ws, "sess-1", ["world-a", "world-b"]))

    worker = gateway.get_worker("wk-1")
    assert worker is not None
    assert worker.session_id == "sess-1"
    assert worker.world_ids == ["world-a", "world-b"]

    assert gateway.get_worker_by_world("world-a") == worker
    assert gateway.get_worker_by_world("world-b") == worker
```

**Run:** `pytest tests/supervisor/test_gateway.py::test_register_worker -v`
**Expected:** FAIL (register_worker not found)

### Step 2: Refactor WorkerController (with backward compatibility stubs)

Replace `src/supervisor/gateway.py` with the new implementation, keeping compatibility stubs for old API:

```python
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WorkerState:
    worker_id: str
    session_id: str
    ws: object
    world_ids: list[str]
    metadata: dict = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"  # "active" | "unreachable" | "dead"


class WorkerController:
    def __init__(self, base_dir: str = "worlds"):
        self._base_dir = base_dir
        self._workers: dict[str, WorkerState] = {}  # worker_id -> WorkerState
        self._world_to_worker: dict[str, str] = {}  # world_id -> worker_id
        self._clients: list = []  # browser/management client websockets
        self._lock = asyncio.Lock()

    # --- New Worker-level API ---

    async def register_worker(self, worker_id: str, ws, session_id: str, world_ids: list[str], metadata: dict | None = None):
        async with self._lock:
            old = self._workers.pop(worker_id, None)
            if old is not None:
                for wid in old.world_ids:
                    self._world_to_worker.pop(wid, None)
                try:
                    await old.ws.close()
                except Exception:
                    pass

            state = WorkerState(
                worker_id=worker_id,
                session_id=session_id,
                ws=ws,
                world_ids=world_ids,
                metadata=metadata or {},
            )
            self._workers[worker_id] = state
            for wid in world_ids:
                self._world_to_worker[wid] = worker_id

            await self._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.session.reset",
                "params": {"worker_id": worker_id, "world_ids": world_ids},
            })

    async def unregister_worker(self, worker_id: str):
        async with self._lock:
            worker = self._workers.pop(worker_id, None)
            if worker is not None:
                for wid in worker.world_ids:
                    self._world_to_worker.pop(wid, None)

    def get_worker(self, worker_id: str) -> WorkerState | None:
        return self._workers.get(worker_id)

    def get_worker_by_world(self, world_id: str) -> WorkerState | None:
        worker_id = self._world_to_worker.get(world_id)
        if worker_id is None:
            return None
        return self._workers.get(worker_id)

    async def send_to_worker(self, worker_id: str, message: dict) -> bool:
        worker = self.get_worker(worker_id)
        if worker is None:
            return False
        ws = worker.ws
        try:
            if hasattr(ws, 'send_str'):
                await ws.send_str(json.dumps(message))
            else:
                await ws.send(json.dumps(message))
            return True
        except Exception:
            return False

    async def send_to_worker_by_world(self, world_id: str, message: dict) -> bool:
        worker = self.get_worker_by_world(world_id)
        if worker is None:
            return False
        return await self.send_to_worker(worker.worker_id, message)

    async def update_heartbeat(self, worker_id: str):
        worker = self._workers.get(worker_id)
        if worker is not None:
            worker.last_heartbeat = datetime.utcnow()

    # --- Backward compatibility stubs (old world-level API) ---
    # These delegate to the new worker-level API for code that hasn't migrated yet.

    async def register_runtime(self, world_id: str, ws, session_id: str):
        """Legacy: treats each world as its own worker."""
        await self.register_worker(world_id, ws, session_id, [world_id])

    def register_runtime_sync(self, world_id: str, ws, session_id: str):
        """Legacy sync wrapper for tests. Only safe in non-async test contexts.

        This method requires a fresh event loop. If called from an async context
        where an event loop is already running, use await register_worker() instead.
        """
        import asyncio
        asyncio.run(self.register_worker(world_id, ws, session_id, [world_id]))

    async def unregister_runtime(self, world_id: str):
        """Legacy: unregisters the worker associated with this world."""
        worker = self.get_worker_by_world(world_id)
        if worker is not None:
            await self.unregister_worker(worker.worker_id)

    def get_runtime(self, world_id: str) -> tuple | None:
        """Legacy: returns (ws, session_id) for the worker managing this world."""
        worker = self.get_worker_by_world(world_id)
        if worker is None:
            return None
        return (worker.ws, worker.session_id)

    async def send_to_runtime(self, world_id: str, message: dict) -> bool:
        """Legacy: delegates to send_to_worker_by_world."""
        return await self.send_to_worker_by_world(world_id, message)

    # --- Client management ---

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

**Run:** `pytest tests/supervisor/test_gateway.py -v`
**Expected:** PASS (old tests still pass via compatibility stubs)

### Step 3: Commit

```bash
rtk git add src/supervisor/gateway.py tests/supervisor/test_gateway.py
rtk git commit -m "refactor: WorkerController worker-level registration with WorkerState"
```

---

## Task 3: Supervisor Server WebSocket Handler

**Files:**
- Modify: `src/supervisor/server.py`

### Step 1: Update /workers WebSocket handler

Modify `_handle_worker_ws` in `src/supervisor/server.py` to handle worker-level notifications:

```python
async def _handle_worker_ws(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    worker_id = None

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            method = data.get("method")
            params = data.get("params", {})

            if method == "notify.worker.activated":
                worker_id = params.get("worker_id")
                session_id = params.get("session_id")
                world_ids = params.get("world_ids", [])
                metadata = params.get("metadata", {})
                if worker_id and session_id:
                    await gateway.register_worker(worker_id, ws, session_id, world_ids, metadata)

            elif method == "notify.worker.heartbeat":
                wid = params.get("worker_id")
                if wid:
                    await gateway.update_heartbeat(wid)

            elif method == "notify.worker.deactivated":
                wid = params.get("worker_id")
                if wid:
                    await gateway.unregister_worker(wid)
                    worker_id = None

        elif msg.type == web.WSMsgType.ERROR:
            break

    if worker_id:
        await gateway.unregister_worker(worker_id)
    return ws
```

### Step 2: Update /api/worlds/{world_id}/stop handler

Fire-and-forget command to Worker (full request/response correlation deferred to follow-up task):

```python
async def _handle_stop(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    worker = gateway.get_worker_by_world(world_id)
    if worker is None:
        return web.json_response({"error": "not_running"}, status=404)

    # Send command and wait for response (simplified: fire-and-forget for now)
    ok = await gateway.send_to_worker_by_world(
        world_id,
        {"jsonrpc": "2.0", "id": 1, "method": "world.stop", "params": {"world_id": world_id}},
    )
    if not ok:
        return web.json_response({"error": "send_failed"}, status=502)
    return web.json_response({"status": "stop_requested"})
```

### Step 3: Add /api/workers endpoint

```python
async def _handle_workers(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    workers = []
    for worker in gateway._workers.values():
        workers.append({
            "worker_id": worker.worker_id,
            "session_id": worker.session_id,
            "world_ids": worker.world_ids,
            "metadata": worker.metadata,
            "status": worker.status,
        })
    return web.json_response({"workers": workers})
```

And register it in `run_supervisor`:
```python
app.router.add_get("/api/workers", _handle_workers)
```

### Step 4: Commit

```bash
rtk git add src/supervisor/server.py
rtk git commit -m "feat: supervisor handles worker-level notifications and routes commands"
```

---

## Task 4: Supervisor Heartbeat Monitor

**Files:**
- Modify: `src/supervisor/gateway.py`
- Modify: `src/supervisor/server.py`

### Step 1: Add heartbeat timeout detection to WorkerController

Add a background coroutine in `WorkerController` that periodically checks for stale heartbeats:

```python
async def start_heartbeat_monitor(self, interval: float = 5.0, timeout: float = 15.0):
    """Periodically check worker heartbeats and mark unreachable ones."""
    while True:
        await asyncio.sleep(interval)
        now = datetime.utcnow()
        dead_workers = []
        for worker_id, worker in list(self._workers.items()):
            if worker.status == "active" and (now - worker.last_heartbeat).total_seconds() > timeout:
                worker.status = "unreachable"
                dead_workers.append(worker)
                # Broadcast disconnection to clients
                await self._broadcast({
                    "jsonrpc": "2.0",
                    "method": "notify.worker.disconnected",
                    "params": {
                        "worker_id": worker_id,
                        "world_ids": worker.world_ids,
                        "reason": "heartbeat_timeout",
                    },
                })
```

### Step 2: Start the monitor in run_supervisor

In `src/supervisor/server.py`, add the monitor to the startup:

```python
def run_supervisor(base_dir="worlds", ws_port=8001, http_port=8080):
    gateway = WorkerController(base_dir=base_dir)
    # Start heartbeat monitor as background task
    asyncio.get_event_loop().create_task(gateway.start_heartbeat_monitor())
    ...
```

### Step 3: Commit

```bash
rtk git add src/supervisor/gateway.py src/supervisor/server.py
rtk git commit -m "feat: add Supervisor heartbeat timeout monitor"
```

---

## Task 5: run_command.py Integration

**Files:**
- Modify: `src/worker/cli/run_command.py`

### Step 1: Refactor run_world to use WorkerManager

Replace `run_world` to load all worlds from the base directory and use `WorkerManager`.

The CLI parameter changes from `--world-dir` to `--base-dir`:

```python
def run_world(base_dir, supervisor_ws=None, ws_port=None, force_stop_on_shutdown=None):
    from src.worker.manager import WorkerManager

    base_dir = os.path.abspath(base_dir)

    # WorkerManager loads all worlds in the base directory
    worker_manager = WorkerManager()
    world_ids = worker_manager.load_worlds(base_dir)

    # Apply force_stop_on_shutdown override if provided
    if force_stop_on_shutdown is not None:
        for bundle in worker_manager.worlds.values():
            bundle["force_stop_on_shutdown"] = force_stop_on_shutdown

    # Start shared scenes for all loaded worlds
    for bundle in worker_manager.worlds.values():
        _start_shared_scenes(bundle)

    # Setup signal handlers
    def _on_signal(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        for world_id in list(worker_manager.worlds.keys()):
            try:
                worker_manager.handle_command("world.stop", {"world_id": world_id})
            except Exception as e:
                print(f"Error stopping {world_id}: {e}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    tasks = []

    async def _start_and_run():
        # Start message hub if any world has one
        for bundle in worker_manager.worlds.values():
            hub = bundle.get("message_hub")
            if hub is not None:
                await hub.start()
                break
        try:
            await asyncio.Future()
        finally:
            for bundle in worker_manager.worlds.values():
                hub = bundle.get("message_hub")
                if hub is not None:
                    await hub.stop()

    tasks.append(loop.create_task(_start_and_run()))

    if ws_port is not None:
        # TODO: Worker-level WebSocket server for direct client connections
        pass

    if supervisor_ws is not None:
        from src.worker.cli.run_command import run_supervisor_client
        tasks.append(loop.create_task(run_supervisor_client(worker_manager, supervisor_ws)))

    try:
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks))
        else:
            loop.run_until_complete(_block_forever())
    finally:
        loop.close()

    return 0
```

### Step 2: Update _run_supervisor_client with independent heartbeat timer

Use `asyncio.gather()` with a dedicated heartbeat coroutine so heartbeats are sent every 5 seconds regardless of incoming messages:

```python
async def run_supervisor_client(worker_manager, supervisor_ws):
    """Connect to Supervisor, register worker, handle commands, send heartbeats.

    This is a module-level export so that run_inline.py can reuse it.
    """
    import websockets

    disconnected_at = None

    while True:
        try:
            async with websockets.connect(supervisor_ws) as ws:
                disconnected_at = None
                conn = JsonRpcConnection(ws)
                _register_worker_handlers(conn, worker_manager)

                # Send worker activation
                metadata = {
                    "pid": os.getpid(),
                    "hostname": os.uname().nodename if hasattr(os, "uname") else "localhost",
                    "started_at": datetime.utcnow().isoformat() + "Z",
                }
                await conn.send(conn.build_notification(
                    "notify.worker.activated",
                    {
                        "worker_id": worker_manager.worker_id,
                        "session_id": worker_manager.session_id,
                        "world_ids": list(worker_manager.worlds.keys()),
                        "metadata": metadata,
                    },
                ))

                # Start message handler and heartbeat in parallel
                await asyncio.gather(
                    _handle_messages(ws, conn, worker_manager),
                    _send_heartbeats(ws, conn, worker_manager),
                    return_exceptions=True,
                )
        except (websockets.exceptions.ConnectionClosed, OSError):
            pass

        # Track disconnect time; if > 15s, self-terminate
        now = asyncio.get_event_loop().time()
        if disconnected_at is None:
            disconnected_at = now
        elif now - disconnected_at > 15:
            print("Supervisor unreachable for 15s, initiating self-termination...")
            for world_id in list(worker_manager.worlds.keys()):
                try:
                    worker_manager.handle_command("world.stop", {"world_id": world_id})
                except Exception:
                    pass
            break

        await asyncio.sleep(5)


async def _handle_messages(ws, conn, worker_manager):
    """Handle incoming messages from Supervisor."""
    while True:
        try:
            raw = await ws.recv()
            msg = json.loads(raw)
            if "id" in msg and ("result" in msg or "error" in msg):
                continue
            resp = await conn.handle_message(raw)
            if resp is not None:
                await conn.send(resp)
        except websockets.exceptions.ConnectionClosed:
            break


async def _send_heartbeats(ws, conn, worker_manager):
    """Send heartbeat every 5 seconds."""
    while True:
        try:
            await asyncio.sleep(5.0)
            if ws.closed:
                break
            # Build heartbeat payload
            worlds_status = {}
            for world_id, bundle in worker_manager.worlds.items():
                sm = bundle["scene_manager"]
                worlds_status[world_id] = {
                    "status": "loaded",
                    "scene_count": len(sm.list_by_world(world_id)),
                    "instance_count": len(bundle["instance_manager"].list(world_id)),
                    "isolated_scenes": [
                        s["scene_id"] for s in sm.list_by_world(world_id)
                        if s.get("mode") == "isolated"
                    ],
                }
            await conn.send(conn.build_notification(
                "notify.worker.heartbeat",
                {
                    "worker_id": worker_manager.worker_id,
                    "session_id": worker_manager.session_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "worlds": worlds_status,
                },
            ))
        except websockets.exceptions.ConnectionClosed:
            break
```

### Step 3: Add command handlers registration

```python
def _register_worker_handlers(conn: JsonRpcConnection, worker_manager):
    async def world_stop(params, req_id):
        return worker_manager.handle_command("world.stop", params)

    async def world_checkpoint(params, req_id):
        return worker_manager.handle_command("world.checkpoint", params)

    async def world_get_status(params, req_id):
        return worker_manager.handle_command("world.getStatus", params)

    async def scene_start(params, req_id):
        return worker_manager.handle_command("scene.start", params)

    async def scene_stop(params, req_id):
        return worker_manager.handle_command("scene.stop", params)

    async def message_hub_publish(params, req_id):
        return worker_manager.handle_command("messageHub.publish", params)

    async def message_hub_publish_batch(params, req_id):
        return worker_manager.handle_command("messageHub.publishBatch", params)

    conn.register("world.stop", world_stop)
    conn.register("world.checkpoint", world_checkpoint)
    conn.register("world.getStatus", world_get_status)
    conn.register("scene.start", scene_start)
    conn.register("scene.stop", scene_stop)
    conn.register("messageHub.publish", message_hub_publish)
    conn.register("messageHub.publishBatch", message_hub_publish_batch)
```

Add import for `datetime`:
```python
from datetime import datetime
```

### Step 4: Update CLI argument parser

In `src/cli/main.py`, change `--world-dir` to `--base-dir` for the `run` command:

```python
run_parser.add_argument(
    "--base-dir", required=True, help="Base directory containing world subdirectories"
)
```

Update `_run_command`:
```python
def _run_command(args):
    from src.worker.cli.run_command import run_world
    return run_world(
        base_dir=args.base_dir,
        supervisor_ws=args.supervisor_ws,
        ws_port=args.ws_port,
        force_stop_on_shutdown=args.force_stop_on_shutdown,
    )
```

### Step 5: Update tests

Modify `tests/worker/cli/test_run_command.py` to test multi-world loading via WorkerManager using `--base-dir`.

### Step 6: Commit

```bash
rtk git add src/worker/cli/run_command.py src/cli/main.py tests/worker/cli/test_run_command.py
rtk git commit -m "feat: run command uses WorkerManager with base_dir, sends worker-level registration and heartbeat"
```

---

## Task 6: run_inline.py Integration

**Files:**
- Modify: `src/worker/cli/run_inline.py`

### Step 1: Refactor run_inline to use WorkerManager with WebSocket loopback

```python
def run_inline(world_dirs, supervisor_ws=None):
    from src.worker.manager import WorkerManager
    from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
    from src.runtime.message_hub import MessageHub

    if not world_dirs:
        return 0

    worker_manager = WorkerManager()

    # Load each specified world
    for world_dir in world_dirs:
        base_dir = os.path.dirname(os.path.abspath(world_dir))
        world_id = os.path.basename(os.path.abspath(world_dir))
        from src.runtime.world_registry import WorldRegistry
        registry = WorldRegistry(base_dir=base_dir)
        bundle = registry.load_world(world_id)
        worker_manager.worlds[world_id] = bundle

    # Setup shared MessageHub
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", "inline")
    msg_store = SQLiteMessageStore(worker_dir)
    message_hub = MessageHub(msg_store, None)

    for world_id, bundle in worker_manager.worlds.items():
        bus = bundle["event_bus_registry"].get_or_create(world_id)
        message_hub.register_world(world_id, bus, bundle.get("model_events", {}))
        bundle["instance_manager"]._message_hub = message_hub
        bundle["message_hub"] = message_hub

    def _shutdown(signum, frame):
        print("Shutting down inline runtime...")
        if message_hub is not None:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(message_hub.stop(), loop)
                else:
                    loop.run_until_complete(message_hub.stop())
            except Exception:
                pass
        for world_id in list(worker_manager.worlds.keys()):
            try:
                worker_manager.handle_command("world.stop", {"world_id": world_id})
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        await message_hub.start()
        try:
            if supervisor_ws is not None:
                # WebSocket loopback connection to Supervisor
                from src.worker.cli.run_command import run_supervisor_client
                await run_supervisor_client(worker_manager, supervisor_ws)
            else:
                await asyncio.Event().wait()
        finally:
            await message_hub.stop()

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()

    return 0
```

**Note:** `_run_supervisor_client` is imported from `run_command.py` to avoid duplication.

### Step 2: Commit

```bash
rtk git add src/worker/cli/run_inline.py tests/worker/cli/test_run_inline.py
rtk git commit -m "feat: run_inline uses WorkerManager, supports WebSocket loopback to Supervisor"
```

---

## Task 7: Integration Tests

**Files:**
- Create: `tests/worker/test_manager_integration.py`
- Create: `tests/supervisor/test_gateway_integration.py`

### Step 1: Test WorkerManager + Supervisor Gateway roundtrip

```python
import pytest
import asyncio
from src.worker.manager import WorkerManager
from src.supervisor.gateway import WorkerController


@pytest.mark.anyio
async def test_worker_registration_roundtrip():
    gateway = WorkerController()

    class FakeWs:
        def __init__(self):
            self.sent = []
            self.closed = False
        async def send_str(self, msg):
            self.sent.append(msg)
        async def close(self):
            self.closed = True

    ws = FakeWs()
    await gateway.register_worker("wk-1", ws, "sess-1", ["world-a"])

    worker = gateway.get_worker("wk-1")
    assert worker.worker_id == "wk-1"
    assert gateway.get_worker_by_world("world-a").worker_id == "wk-1"

    await gateway.unregister_worker("wk-1")
    assert gateway.get_worker("wk-1") is None
    assert gateway.get_worker_by_world("world-a") is None
```

**Run:** `pytest tests/supervisor/test_gateway_integration.py -v`
**Expected:** PASS

### Step 2: Commit

```bash
rtk git add tests/worker/test_manager_integration.py tests/supervisor/test_gateway_integration.py
rtk git commit -m "test: add integration tests for Worker-Supervisor registration"
```

---

## Task 8: Final Verification

### Step 1: Run all tests

```bash
rtk pytest tests/supervisor/ tests/worker/ -v
```

**Expected:** All tests pass

### Step 2: Commit

```bash
rtk git commit --allow-empty -m "chore: complete Worker-Supervisor registration refactor"
```
