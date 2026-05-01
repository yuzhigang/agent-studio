# Frontend API Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement REST API on Supervisor for frontend management console. Worker commands are already in place via `src/worker/commands/`.

**Architecture:** Supervisor exposes REST endpoints that proxy to Worker JSON-RPC commands. Handlers are split by domain under `src/supervisor/handlers/`. Supervisor caches world state from heartbeats and pushes change notifications via WebSocket.

**Tech Stack:** Python, aiohttp, pytest, JSON-RPC over WebSocket

---

## File Structure

| File | Responsibility |
|---|---|
| `src/supervisor/worker.py` | WorkerController, world state cache, WebSocket broadcast |
| `src/supervisor/handlers/__init__.py` | Export all handlers |
| `src/supervisor/handlers/workers.py` | GET /api/workers, GET /api/workers/{id}/worlds |
| `src/supervisor/handlers/worlds.py` | world start/stop/checkpoint/detail |
| `src/supervisor/handlers/instances.py` | instances list/detail |
| `src/supervisor/handlers/scenes.py` | scenes list/start/stop, scene instances |
| `src/supervisor/handlers/models.py` | models list/detail |
| `src/supervisor/server.py` | aiohttp app setup, route registration |
| `tests/supervisor/test_api.py` | Unit tests for Supervisor REST handlers |

---

## Task 1: Supervisor — Add HTTP Proxy and World State Cache

**Files:**
- Modify: `src/supervisor/worker.py`
- Modify: `src/supervisor/server.py` (heartbeat handler)

- [ ] **Step 1: Add world status cache to WorkerController**

In `src/supervisor/worker.py`, modify `WorkerController.__init__`:

```python
    def __init__(self, base_dir: str = "worlds"):
        self._base_dir = base_dir
        self._workers: dict[str, WorkerState] = {}
        self._world_to_worker: dict[str, str] = {}
        self._clients: list = []
        self._lock = asyncio.Lock()
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._world_status_cache: dict[str, dict] = {}  # world_id -> latest status from heartbeat
```

- [ ] **Step 2: Add `WorkerRpcError` exception and update error handling**

In `src/supervisor/worker.py`, add:

```python
class WorkerRpcError(RuntimeError):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
```

Update `_handle_response` to raise `WorkerRpcError`:

```python
    def _handle_response(self, response: dict) -> None:
        req_id = response.get("id")
        if req_id is None:
            return
        future = self._pending_requests.pop(req_id, None)
        if future is None:
            return
        if "error" in response:
            error = response["error"]
            future.set_exception(WorkerRpcError(
                error.get("code", 0),
                error.get("message", "Unknown error")
            ))
        else:
            future.set_result(response.get("result"))
```

- [ ] **Step 3: Add proxy method for REST -> JSON-RPC**

In `src/supervisor/worker.py`, add to `WorkerController`:

```python
    async def proxy_to_worker(self, world_id: str, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request to the worker managing world_id and return the result."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        return await self.send_request(world_id, message)
```

- [ ] **Step 4: Update heartbeat handler to cache world status**

In `src/supervisor/worker.py`, modify `update_heartbeat`:

```python
    async def update_heartbeat(self, worker_id: str, worlds_status: dict | None = None):
        worker = self._workers.get(worker_id)
        if worker is not None:
            worker.last_heartbeat = datetime.now(timezone.utc)
        if worlds_status:
            for world_id, status in worlds_status.items():
                old = self._world_status_cache.get(world_id, {})
                new_status = status.get("status")
                old_status = old.get("status")
                if new_status != old_status:
                    await self._broadcast({
                        "jsonrpc": "2.0",
                        "method": "notify.world.status_changed",
                        "params": {
                            "world_id": world_id,
                            "status": new_status,
                            "previous_status": old_status,
                            "reason": "heartbeat",
                        },
                    })
                self._world_status_cache[world_id] = status
```

- [ ] **Step 5: Update `register_worker` and `unregister_worker` broadcasts**

In `src/supervisor/worker.py`, update `register_worker` to broadcast `notify.worker.activated`:

```python
            await self._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.worker.activated",
                "params": {
                    "worker_id": worker_id,
                    "session_id": session_id,
                    "world_ids": world_ids,
                    "metadata": metadata or {},
                },
            })
```

Update `unregister_worker` to broadcast `notify.worker.disconnected`:

```python
    async def unregister_worker(self, worker_id: str):
        async with self._lock:
            worker = self._workers.pop(worker_id, None)
            if worker is not None:
                for wid in worker.world_ids:
                    self._world_to_worker.pop(wid, None)
                await self._broadcast({
                    "jsonrpc": "2.0",
                    "method": "notify.worker.disconnected",
                    "params": {
                        "worker_id": worker_id,
                        "world_ids": worker.world_ids,
                        "reason": "explicit_deactivation",
                    },
                })
```

- [ ] **Step 6: Update server.py heartbeat handler to pass worlds data**

In `src/supervisor/server.py`, modify the heartbeat handler:

```python
            elif method == "notify.worker.heartbeat":
                wid = params.get("worker_id")
                worlds = params.get("worlds", {})
                if wid:
                    await gateway.update_heartbeat(wid, worlds)
```

- [ ] **Step 7: Commit**

```bash
git add src/supervisor/worker.py src/supervisor/server.py
git commit -m "feat: add Supervisor world state cache, proxy, and status broadcast"
```

---

## Task 2: Scaffold `src/supervisor/handlers/` Package

**Files:**
- Create: `src/supervisor/handlers/__init__.py`
- Create: `src/supervisor/handlers/workers.py`
- Create: `src/supervisor/handlers/worlds.py`
- Create: `src/supervisor/handlers/instances.py`
- Create: `src/supervisor/handlers/scenes.py`
- Create: `src/supervisor/handlers/models.py`

- [ ] **Step 1: Create handler files with stubs**

`src/supervisor/handlers/__init__.py`:

```python
from src.supervisor.handlers.workers import handle_workers, handle_worker_worlds
from src.supervisor.handlers.worlds import (
    handle_world_start,
    handle_world_stop,
    handle_world_checkpoint,
    handle_world_detail,
)
from src.supervisor.handlers.instances import handle_world_instances, handle_instance_detail
from src.supervisor.handlers.scenes import handle_world_scenes, handle_scene_instances, handle_scene_start, handle_scene_stop
from src.supervisor.handlers.models import handle_world_models, handle_model_detail
```

Each domain file starts with a stub, e.g. `workers.py`:

```python
from aiohttp import web

async def handle_workers(request: web.Request):
    raise NotImplementedError

async def handle_worker_worlds(request: web.Request):
    raise NotImplementedError
```

(Same pattern for all other files.)

- [ ] **Step 2: Commit**

```bash
git add src/supervisor/handlers/
git commit -m "chore: scaffold supervisor handlers package"
```

---

## Task 3: Supervisor — Implement REST API Handlers

**Files:**
- Modify: `src/supervisor/handlers/*.py`
- Modify: `src/supervisor/server.py` (add shared helpers)
- Test: `tests/supervisor/test_api.py`

- [ ] **Step 1: Add shared error mapping helper**

Add at module level in `src/supervisor/server.py`:

```python
from src.supervisor.worker import WorkerRpcError

_RPC_ERROR_MAP = {
    -32004: 404,  # World/Scene/Instance not found
    -32003: 409,  # Illegal lifecycle
    -32002: 404,  # Scene not found
    -32001: 409,  # World locked
    -32602: 400,  # Invalid params
    -32601: 501,  # Method not found
}

def _rpc_code_to_http(code: int) -> int:
    return _RPC_ERROR_MAP.get(code, 502)
```

- [ ] **Step 2: Implement `workers.py`**

```python
from aiohttp import web
from src.supervisor.worker import WorkerController


async def handle_workers(request: web.Request):
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
    return web.json_response({"items": workers, "total": len(workers)})


async def handle_worker_worlds(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    worker_id = request.match_info["worker_id"]
    worker = gateway.get_worker(worker_id)
    if worker is None:
        return web.json_response({"error": "worker_not_found"}, status=404)

    worlds = []
    for world_id in worker.world_ids:
        world_data = gateway._world_status_cache.get(world_id, {})
        worlds.append({
            "world_id": world_id,
            "status": world_data.get("status", "unknown"),
            "scene_count": world_data.get("scene_count", 0),
            "instance_count": world_data.get("instance_count", 0),
        })
    return web.json_response({"items": worlds, "total": len(worlds)})
```

- [ ] **Step 3: Implement `worlds.py`**

```python
import subprocess

from aiohttp import web
from src.supervisor.server import _build_runtime_cmd, _rpc_code_to_http
from src.supervisor.worker import WorkerController, WorkerRpcError


async def handle_world_start(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    ws_port = request.app["ws_port"]
    world_id = request.match_info["world_id"]
    worker = gateway.get_worker_by_world(world_id)
    if worker is not None:
        return web.json_response({"status": "already_running"})

    world_dir = f"{gateway._base_dir}/{world_id}"
    supervisor_ws = f"ws://localhost:{ws_port}/workers"
    cmd = _build_runtime_cmd(world_dir, supervisor_ws)
    subprocess.Popen(cmd)
    return web.json_response({"status": "starting"})


async def handle_world_stop(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    try:
        result = await gateway.proxy_to_worker(world_id, "world.stop", {"world_id": world_id})
        if result.get("status") == "stopped":
            previous = gateway._world_status_cache.get(world_id, {}).get("status")
            await gateway._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.world.status_changed",
                "params": {
                    "world_id": world_id,
                    "status": "stopped",
                    "previous_status": previous,
                    "reason": "user_request",
                },
            })
            gateway._world_status_cache[world_id] = {"status": "stopped"}
        return web.json_response(result)
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_world_checkpoint(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    try:
        result = await gateway.proxy_to_worker(world_id, "world.checkpoint", {"world_id": world_id})
        return web.json_response(result)
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_world_detail(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    worker = gateway.get_worker_by_world(world_id)
    if worker is None:
        return web.json_response({"error": "world_not_found"}, status=404)

    try:
        result = await gateway.proxy_to_worker(world_id, "world.getStatus", {"world_id": world_id})
        status = result.get("status", "unknown")
        scenes = result.get("scenes", [])

        instances_result = await gateway.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instance_count = len(instances_result.get("instances", []))

        return web.json_response({
            "world_id": world_id,
            "worker_id": worker.worker_id,
            "status": status,
            "scenes": scenes,
            "instance_count": instance_count,
        })
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)
```

- [ ] **Step 4: Implement `instances.py`**

```python
from aiohttp import web
from src.supervisor.server import _rpc_code_to_http
from src.supervisor.worker import WorkerController, WorkerRpcError


async def handle_world_instances(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]

    try:
        result = await gateway.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instances = result.get("instances", [])

        model_id = request.query.get("model_id")
        scope = request.query.get("scope")
        lifecycle_state = request.query.get("lifecycle_state")
        state = request.query.get("state")

        filtered = []
        for inst in instances:
            if model_id and inst.get("model") != model_id:
                continue
            if scope and inst.get("scope") != scope:
                continue
            if lifecycle_state and inst.get("lifecycle_state") != lifecycle_state:
                continue
            raw_state = inst.get("state", {})
            inst_state = raw_state.get("current") if isinstance(raw_state, dict) else raw_state
            if state and inst_state != state:
                continue
            filtered.append({
                "instance_id": inst["id"],
                "model_name": inst["model"],
                "scope": inst["scope"],
                "state": inst_state,
                "lifecycle_state": inst["lifecycle_state"],
                "variables": inst.get("variables", {}),
                "attributes": inst.get("attributes", {}),
            })

        return web.json_response({"items": filtered, "total": len(filtered)})
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_instance_detail(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    instance_id = request.match_info["instance_id"]

    try:
        result = await gateway.proxy_to_worker(
            world_id, "world.instances.get", {"world_id": world_id, "instance_id": instance_id}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "instance_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)
```

- [ ] **Step 5: Implement `scenes.py`**

```python
from aiohttp import web
from src.supervisor.server import _rpc_code_to_http
from src.supervisor.worker import WorkerController, WorkerRpcError


async def handle_world_scenes(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]

    try:
        result = await gateway.proxy_to_worker(world_id, "world.scenes.list", {"world_id": world_id})
        scenes = result.get("scenes", [])
        return web.json_response({"items": scenes, "total": len(scenes)})
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_scene_instances(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]

    try:
        result = await gateway.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instances = result.get("instances", [])

        model_id = request.query.get("model_id")
        lifecycle_state = request.query.get("lifecycle_state")
        state = request.query.get("state")

        target_scope = f"scene:{scene_id}"
        filtered = []
        for inst in instances:
            if inst.get("scope") != target_scope:
                continue
            if model_id and inst.get("model") != model_id:
                continue
            if lifecycle_state and inst.get("lifecycle_state") != lifecycle_state:
                continue
            raw_state = inst.get("state", {})
            inst_state = raw_state.get("current") if isinstance(raw_state, dict) else raw_state
            if state and inst_state != state:
                continue
            filtered.append({
                "instance_id": inst["id"],
                "model_name": inst["model"],
                "scope": inst["scope"],
                "state": inst_state,
                "lifecycle_state": inst["lifecycle_state"],
                "variables": inst.get("variables", {}),
                "attributes": inst.get("attributes", {}),
            })

        return web.json_response({"items": filtered, "total": len(filtered)})
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_scene_start(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]
    try:
        result = await gateway.proxy_to_worker(
            world_id, "scene.start", {"world_id": world_id, "scene_id": scene_id}
        )
        if result.get("status") == "started":
            previous = gateway._world_status_cache.get(world_id, {}).get("status")
            await gateway._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.world.status_changed",
                "params": {
                    "world_id": world_id,
                    "status": "running",
                    "previous_status": previous,
                    "reason": "scene_started",
                },
            })
        return web.json_response(result)
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)


async def handle_scene_stop(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]
    try:
        result = await gateway.proxy_to_worker(
            world_id, "scene.stop", {"world_id": world_id, "scene_id": scene_id}
        )
        if result.get("status") == "stopped":
            previous = gateway._world_status_cache.get(world_id, {}).get("status")
            await gateway._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.world.status_changed",
                "params": {
                    "world_id": world_id,
                    "status": "running",
                    "previous_status": previous,
                    "reason": "scene_stopped",
                },
            })
        return web.json_response(result)
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        if e.code == -32002:
            return web.json_response({"error": "scene_not_found", "message": e.message}, status=status)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
```

- [ ] **Step 6: Implement `models.py`**

```python
from aiohttp import web
from src.supervisor.server import _rpc_code_to_http
from src.supervisor.worker import WorkerController, WorkerRpcError


async def handle_world_models(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]

    try:
        result = await gateway.proxy_to_worker(world_id, "world.models.list", {"world_id": world_id})
        models = result.get("models", [])
        return web.json_response({"items": models, "total": len(models)})
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_model_detail(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    model_id = request.match_info["model_id"]

    try:
        result = await gateway.proxy_to_worker(
            world_id, "world.models.get", {"world_id": world_id, "model_id": model_id}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = _rpc_code_to_http(e.code)
        return web.json_response({"error": "model_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)
```

- [ ] **Step 7: Add handler tests**

```python
import pytest
from aiohttp import web
from src.supervisor.worker import WorkerController


@pytest.fixture
def gateway():
    return WorkerController(base_dir="test_worlds")


@pytest.fixture
def app(gateway):
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = 8001
    app["http_port"] = 8080
    return app


@pytest.mark.anyio
async def test_get_worker_worlds_not_found(app):
    from src.supervisor.handlers.workers import handle_worker_worlds
    request = type("Req", (), {"app": app, "match_info": {"worker_id": "nonexistent"}})()
    response = await handle_worker_worlds(request)
    assert response.status == 404


@pytest.mark.anyio
async def test_get_world_instances_with_filter(app):
    from src.supervisor.handlers.instances import handle_world_instances

    gateway = app["gateway"]
    async def mock_proxy(world_id, method, params=None):
        return {
            "instances": [
                {"id": "i1", "model": "robot", "scope": "world", "state": {"current": "idle"}, "lifecycle_state": "active"},
                {"id": "i2", "model": "car", "scope": "world", "state": {"current": "busy"}, "lifecycle_state": "active"},
            ]
        }
    gateway.proxy_to_worker = mock_proxy
    gateway._workers["worker1"] = type("W", (), {"worker_id": "worker1", "world_ids": ["w1"]})()
    gateway._world_to_worker["w1"] = "worker1"

    request = type("Req", (), {
        "app": app,
        "match_info": {"world_id": "w1"},
        "query": {"model_id": "robot"},
    })()
    response = await handle_world_instances(request)
    assert response.status == 200
    data = await response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["instance_id"] == "i1"
    assert data["items"][0]["state"] == "idle"


@pytest.mark.anyio
async def test_post_world_stop_triggers_broadcast(app):
    from src.supervisor.handlers.worlds import handle_world_stop

    gateway = app["gateway"]
    broadcasts = []
    gateway._broadcast = lambda msg: broadcasts.append(msg)
    gateway._world_status_cache["w1"] = {"status": "running"}

    async def mock_proxy(world_id, method, params=None):
        return {"status": "stopped"}
    gateway.proxy_to_worker = mock_proxy
    gateway._workers["worker1"] = type("W", (), {"worker_id": "worker1"})()
    gateway._world_to_worker["w1"] = "worker1"

    request = type("Req", (), {"app": app, "match_info": {"world_id": "w1"}})()
    response = await handle_world_stop(request)
    assert response.status == 200
    assert len(broadcasts) == 1
    assert broadcasts[0]["method"] == "notify.world.status_changed"
```

- [ ] **Step 8: Commit**

```bash
git add src/supervisor/handlers/ tests/supervisor/test_api.py
git commit -m "feat: implement all Supervisor REST API handlers"
```

---

## Task 4: Supervisor — Register REST API Routes

**Files:**
- Modify: `src/supervisor/server.py`

- [ ] **Step 1: Update route registration in `run_supervisor`**

In `run_supervisor` function, import handlers and register routes:

```python
from src.supervisor import handlers

# ... inside run_supervisor ...
    app.router.add_get("/api/workers", handlers.handle_workers)
    app.router.add_get("/api/workers/{worker_id}/worlds", handlers.handle_worker_worlds)
    app.router.add_get("/api/worlds/{world_id}", handlers.handle_world_detail)
    app.router.add_post("/api/worlds/{world_id}/start", handlers.handle_world_start)
    app.router.add_post("/api/worlds/{world_id}/stop", handlers.handle_world_stop)
    app.router.add_post("/api/worlds/{world_id}/checkpoint", handlers.handle_world_checkpoint)
    app.router.add_get("/api/worlds/{world_id}/instances", handlers.handle_world_instances)
    app.router.add_get("/api/worlds/{world_id}/instances/{instance_id}", handlers.handle_instance_detail)
    app.router.add_get("/api/worlds/{world_id}/models", handlers.handle_world_models)
    app.router.add_get("/api/worlds/{world_id}/models/{model_id}", handlers.handle_model_detail)
    app.router.add_get("/api/worlds/{world_id}/scenes", handlers.handle_world_scenes)
    app.router.add_get("/api/worlds/{world_id}/scenes/{scene_id}/instances", handlers.handle_scene_instances)
    app.router.add_post("/api/worlds/{world_id}/scenes/{scene_id}/start", handlers.handle_scene_start)
    app.router.add_post("/api/worlds/{world_id}/scenes/{scene_id}/stop", handlers.handle_scene_stop)
```

Also remove the old handler functions from the file (`_handle_start`, `_handle_stop`, `_handle_list_instances`, `_handle_workers`).

- [ ] **Step 2: Commit**

```bash
git add src/supervisor/server.py
git commit -m "feat: register REST API routes and update response format"
```

---

## Task 5: Integration Testing

**Files:**
- Test: `tests/supervisor/test_integration.py`

- [ ] **Step 1: Write integration test for full flow**

```python
import pytest


@pytest.mark.anyio
async def test_full_api_flow():
    from src.supervisor.worker import WorkerController
    from src.supervisor.handlers.workers import handle_workers
    from aiohttp import web

    gateway = WorkerController(base_dir="test_worlds")
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = 8001
    app["http_port"] = 8080

    request = type("Req", (), {"app": app})()
    response = await handle_workers(request)
    assert response.status == 200
    data = await response.json()
    assert "items" in data
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/supervisor/test_api.py tests/supervisor/test_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: add integration tests for frontend API"
```

---

## Task 6: Final Review and Cleanup

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS (except known Windows file-lock failures)

- [ ] **Step 2: Verify spec compliance**

Check that all endpoints from `docs/superpowers/specs/2026-04-30-frontend-api-design.md` are implemented:
- [ ] GET /api/workers
- [ ] GET /api/workers/{worker_id}/worlds
- [ ] GET /api/worlds/{world_id}
- [ ] POST /api/worlds/{world_id}/start
- [ ] POST /api/worlds/{world_id}/stop
- [ ] POST /api/worlds/{world_id}/checkpoint
- [ ] GET /api/worlds/{world_id}/models
- [ ] GET /api/worlds/{world_id}/models/{model_id}
- [ ] GET /api/worlds/{world_id}/instances
- [ ] GET /api/worlds/{world_id}/instances/{instance_id}
- [ ] GET /api/worlds/{world_id}/scenes
- [ ] GET /api/worlds/{world_id}/scenes/{scene_id}/instances
- [ ] POST /api/worlds/{world_id}/scenes/{scene_id}/start
- [ ] POST /api/worlds/{world_id}/scenes/{scene_id}/stop
- [ ] WebSocket broadcasts (heartbeat, worker status, world status changes)

- [ ] **Step 3: Commit any final fixes**

```bash
git add .
git commit -m "feat: complete frontend API implementation"
```
