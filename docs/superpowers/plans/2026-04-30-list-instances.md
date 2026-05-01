# List Instances Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI command and HTTP API to list all instances and their states in a running world, querying across the supervisor-worker network boundary.

**Architecture:** Worker exposes a new JSON-RPC method `world.instances.list` that reads from `InstanceManager`. Supervisor gains request-response capability over WebSocket to forward HTTP requests to workers. CLI calls the supervisor HTTP API.

**Tech Stack:** Python, aiohttp (supervisor), websockets (worker), JSON-RPC 2.0, pytest

---

## File Structure

| File | Responsibility |
|---|---|
| `src/worker/manager.py` | Add `world.instances.list` command handling in `WorkerManager.handle_command` |
| `src/worker/cli/run_command.py` | Register `world.instances.list` JSON-RPC handler |
| `src/supervisor/worker.py` | Add request-response mechanism (`send_request`, pending requests map) to `WorkerController` |
| `src/supervisor/server.py` | Add `GET /api/worlds/{world_id}/instances` HTTP route in `run_supervisor` |
| `src/cli/main.py` | Add `list-instances` subcommand |
| `tests/supervisor/test_worker_controller.py` | Unit tests for request-response mechanism |
| `tests/worker/test_manager_commands.py` | Unit tests for `world.instances.list` command |

---

## Task 1: Worker Command — `world.instances.list`

**Files:**
- Modify: `src/worker/manager.py:174-303`
- Modify: `src/worker/cli/run_command.py:272-304`
- Test: `tests/worker/test_manager_commands.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/worker/test_manager_commands.py
import pytest
from src.worker.manager import WorkerManager


@pytest.fixture
def manager_with_world():
    mgr = WorkerManager()
    mgr.worlds["test-world"] = {
        "world_id": "test-world",
        "instance_manager": MockInstanceManager(),
    }
    return mgr


class MockInstanceManager:
    def list_by_world(self, world_id):
        from src.runtime.instance import Instance
        return [
            Instance(
                instance_id="inst-1",
                model_name="model-a",
                world_id=world_id,
                scope="world",
                state={"current": "idle", "enteredAt": "2026-04-30T00:00:00"},
                lifecycle_state="active",
                variables={"count": 0},
                attributes={"capacity": 100},
            ),
        ]


@pytest.mark.anyio
async def test_world_instances_list(manager_with_world):
    result = await manager_with_world.handle_command(
        "world.instances.list", {"world_id": "test-world"}
    )
    assert "instances" in result
    assert len(result["instances"]) == 1
    inst = result["instances"][0]
    assert inst["id"] == "inst-1"
    assert inst["model"] == "model-a"
    assert inst["state"] == "idle"
    assert inst["scope"] == "world"
    assert inst["lifecycle_state"] == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/worker/test_manager_commands.py::test_world_instances_list -v`

Expected: FAIL with `JsonRpcError: Unknown method: world.instances.list`

- [ ] **Step 3: Implement `world.instances.list` in WorkerManager**

In `src/worker/manager.py`, inside `handle_command`, before the final `raise JsonRpcError(-32601, ...)`:

```python
if method == "world.instances.list":
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    instances = bundle["instance_manager"].list_by_world(world_id)
    return {
        "instances": [
            {
                "id": inst.instance_id,
                "model": inst.model_name,
                "scope": inst.scope,
                "state": inst.state.get("current"),
                "lifecycle_state": inst.lifecycle_state,
                "variables": inst.variables,
                "attributes": inst.attributes,
            }
            for inst in instances
        ]
    }
```

- [ ] **Step 4: Register handler in worker JSON-RPC**

In `src/worker/cli/run_command.py`, inside `_register_worker_handlers`, after `world_get_status`:

```python
async def world_instances_list(params, req_id):
    return await worker_manager.handle_command("world.instances.list", params)

conn.register("world.instances.list", world_instances_list)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/worker/test_manager_commands.py::test_world_instances_list -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/worker/test_manager_commands.py src/worker/manager.py src/worker/cli/run_command.py
git commit -m "feat: add world.instances.list JSON-RPC command"
```

---

## Task 2: Supervisor Request-Response Mechanism

**Files:**
- Modify: `src/supervisor/worker.py`
- Test: `tests/supervisor/test_worker_controller.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/supervisor/test_worker_controller.py
import pytest
import asyncio
from unittest.mock import AsyncMock

from src.supervisor.worker import WorkerController


@pytest.fixture
def controller():
    return WorkerController(base_dir="worlds")


@pytest.fixture
def mock_worker_ws():
    ws = AsyncMock()
    ws.closed = False
    return ws


@pytest.mark.anyio
async def test_send_request_success(controller, mock_worker_ws):
    # Register a mock worker
    await controller.register_worker(
        "wk-1", mock_worker_ws, "sess-1", ["world-1"]
    )

    # Simulate worker responding in background
    async def delayed_response():
        await asyncio.sleep(0.05)
        # Simulate the response handler being called
        future = list(controller._pending_requests.values())[0]
        future.set_result({"instances": [{"id": "inst-1"}]})

    asyncio.create_task(delayed_response())

    result = await controller.send_request("world-1", {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "world.instances.list",
        "params": {"world_id": "world-1"},
    })

    assert result == {"instances": [{"id": "inst-1"}]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/supervisor/test_worker_controller.py::test_send_request_success -v`

Expected: FAIL with `AttributeError: 'WorkerController' object has no attribute 'send_request'`

- [ ] **Step 3: Implement request-response mechanism**

In `src/supervisor/worker.py`:

Add imports at top:
```python
import uuid
```

Add to `WorkerController.__init__`:
```python
self._pending_requests: dict[str, asyncio.Future] = {}
```

Add method `send_request`:
```python
async def send_request(self, world_id: str, message: dict, timeout: float = 5.0) -> dict:
    """Send a JSON-RPC request to a worker and wait for its response.

    Returns the response result dict. Raises TimeoutError or RuntimeError on failure.
    """
    worker = self.get_worker_by_world(world_id)
    if worker is None:
        raise RuntimeError(f"No worker running world {world_id}")

    # Generate a unique request ID if not present
    req_id = message.get("id")
    if req_id is None:
        req_id = str(uuid.uuid4())
        message = {**message, "id": req_id}

    future = asyncio.get_event_loop().create_future()
    self._pending_requests[req_id] = future

    try:
        ok = await self.send_to_worker(worker.worker_id, message)
        if not ok:
            raise RuntimeError(f"Failed to send request to worker {worker.worker_id}")

        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    finally:
        self._pending_requests.pop(req_id, None)
```

Add method `_handle_response`:
```python
def _handle_response(self, response: dict) -> None:
    """Handle an incoming JSON-RPC response from a worker."""
    req_id = response.get("id")
    if req_id is None:
        return
    future = self._pending_requests.pop(req_id, None)
    if future is None:
        return
    if "error" in response:
        future.set_exception(RuntimeError(response["error"].get("message", "Unknown error")))
    else:
        future.set_result(response.get("result"))
```

Update `_handle_worker_ws` in `server.py` (Step 4 will do this) to call `_handle_response`.

- [ ] **Step 4: Update worker WebSocket handler to route responses**

In `src/supervisor/server.py`, inside `_handle_worker_ws`, add handling for JSON-RPC responses:

After the existing `if msg.type == web.WSMsgType.TEXT:` block's method dispatch, add:

```python
# Handle JSON-RPC responses (from worker to supervisor)
if "id" in data and ("result" in data or "error" in data):
    gateway._handle_response(data)
    continue
```

This goes before the existing `method = data.get("method")` line. Reorder the handler:

```python
async def _handle_worker_ws(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    worker_id = None

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)

            # Handle JSON-RPC responses from worker
            if "id" in data and ("result" in data or "error" in data):
                gateway._handle_response(data)
                continue

            method = data.get("method")
            params = data.get("params", {})

            # existing notification handlers...
            if method == "notify.worker.activated":
                ...
            elif method == "notify.worker.heartbeat":
                ...
            elif method == "notify.worker.deactivated":
                ...

        elif msg.type == web.WSMsgType.ERROR:
            break

    if worker_id:
        await gateway.unregister_worker(worker_id)
    return ws
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/supervisor/test_worker_controller.py::test_send_request_success -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/supervisor/test_worker_controller.py src/supervisor/worker.py src/supervisor/server.py
git commit -m "feat: add supervisor request-response over WebSocket"
```

---

## Task 3: HTTP API — `GET /api/worlds/{world_id}/instances`

**Files:**
- Modify: `src/supervisor/server.py`
- Test: `tests/supervisor/test_server.py` (modify or create)

- [ ] **Step 1: Write the failing test**

```python
# tests/supervisor/test_server.py
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from src.supervisor.server import run_supervisor
from src.supervisor.worker import WorkerController


class TestListInstances(AioHTTPTestCase):
    async def get_application(self):
        gateway = WorkerController(base_dir="worlds")
        app = web.Application()
        app["gateway"] = gateway
        app["ws_port"] = 8001
        app["http_port"] = 8080
        app.router.add_get("/api/worlds/{world_id}/instances", _handle_list_instances)
        return app

    @unittest_run_loop
    async def test_list_instances_no_worker(self):
        resp = await self.client.request("GET", "/api/worlds/test-world/instances")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/supervisor/test_server.py::TestListInstances::test_list_instances_no_worker -v`

Expected: FAIL with `NameError: name '_handle_list_instances' is not defined`

- [ ] **Step 3: Implement HTTP handler**

In `src/supervisor/server.py`, add handler after `_handle_workers`:

```python
async def _handle_list_instances(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]

    worker = gateway.get_worker_by_world(world_id)
    if worker is None:
        return web.json_response({"error": "not_running"}, status=404)

    try:
        result = await gateway.send_request(
            world_id,
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "world.instances.list",
                "params": {"world_id": world_id},
            },
        )
        return web.json_response(result)
    except TimeoutError:
        return web.json_response({"error": "timeout"}, status=504)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=502)
```

Add import at top of `server.py`:
```python
import uuid
```

Register route in `run_supervisor`:
```python
app.router.add_get("/api/worlds/{world_id}/instances", _handle_list_instances)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/supervisor/test_server.py::TestListInstances::test_list_instances_no_worker -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/supervisor/test_server.py src/supervisor/server.py
git commit -m "feat: add GET /api/worlds/{world_id}/instances HTTP endpoint"
```

---

## Task 4: CLI Command — `list-instances`

**Files:**
- Modify: `src/cli/main.py`
- Test: `tests/cli/test_main.py` (modify or create)

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_main.py
from unittest.mock import patch, MagicMock
import pytest
from src.cli.main import main


def test_list_instances_no_args():
    with pytest.raises(SystemExit):
        main(["list-instances"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_list_instances_no_args -v`

Expected: FAIL with `SystemExit: 2` (argparse error because subcommand doesn't exist)

- [ ] **Step 3: Implement CLI command**

In `src/cli/main.py`, add imports:
```python
import json
import urllib.request
```

Add subparser after `sync_parser`:
```python
list_parser = subparsers.add_parser(
    "list-instances", help="List all instances in a running world"
)
list_parser.add_argument("--world-id", required=True, help="World ID")
list_parser.add_argument(
    "--supervisor-url", default="http://localhost:8080", help="Supervisor HTTP URL"
)
list_parser.set_defaults(func=_list_instances_command)
```

Add handler function:
```python
def _list_instances_command(args):
    url = f"{args.supervisor_url}/api/worlds/{args.world_id}/instances"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} - {e.reason}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    instances = data.get("instances", [])
    if not instances:
        print(f"No instances found in world '{args.world_id}'")
        return 0

    print(f"Instances in world '{args.world_id}':")
    print(f"{'ID':<20} {'Model':<20} {'Scope':<10} {'State':<15} {'Lifecycle':<10}")
    print("-" * 80)
    for inst in instances:
        print(
            f"{inst['id']:<20} {inst['model']:<20} {inst['scope']:<10} "
            f"{inst.get('state', 'N/A'):<15} {inst.get('lifecycle_state', 'N/A'):<10}"
        )
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py::test_list_instances_no_args -v`

Expected: PASS (argparse validates required args)

- [ ] **Step 5: Commit**

```bash
git add tests/cli/test_main.py src/cli/main.py
git commit -m "feat: add list-instances CLI command"
```

---

## Task 5: Integration Test

**Files:**
- Create: `tests/integration/test_list_instances.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_list_instances.py
import pytest
import asyncio
from unittest.mock import AsyncMock

from src.supervisor.worker import WorkerController


@pytest.mark.anyio
async def test_end_to_end_list_instances():
    """Test the full flow: supervisor receives HTTP request, forwards to worker, worker responds."""
    gateway = WorkerController(base_dir="worlds")

    # Mock worker WebSocket
    mock_ws = AsyncMock()
    mock_ws.closed = False

    await gateway.register_worker(
        "wk-1", mock_ws, "sess-1", ["demo-world"]
    )

    # Start send_request in background
    request_task = asyncio.create_task(gateway.send_request("demo-world", {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "world.instances.list",
        "params": {"world_id": "demo-world"},
    }))

    # Wait a tick for the request to be registered
    await asyncio.sleep(0.01)

    # Simulate worker response
    gateway._handle_response({
        "jsonrpc": "2.0",
        "id": 42,
        "result": {
            "instances": [
                {"id": "sensor-01", "model": "heartbeat", "state": "idle"},
            ]
        },
    })

    result = await request_task
    assert result["instances"][0]["id"] == "sensor-01"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/integration/test_list_instances.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_list_instances.py
git commit -m "test: add integration test for list-instances flow"
```

---

## Task 6: Run Full Test Suite

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: All existing tests pass + new tests pass

- [ ] **Step 2: Commit any fixes**

If failures, fix and commit.

---

## Test Summary

| Test | File | What it covers |
|---|---|---|
| `test_world_instances_list` | `tests/worker/test_manager_commands.py` | Worker command returns instance data |
| `test_send_request_success` | `tests/supervisor/test_worker_controller.py` | Supervisor request-response round-trip |
| `test_list_instances_no_worker` | `tests/supervisor/test_server.py` | HTTP 404 when world not running |
| `test_list_instances_no_args` | `tests/cli/test_main.py` | CLI arg validation |
| `test_end_to_end_list_instances` | `tests/integration/test_list_instances.py` | Full supervisor-worker flow |
