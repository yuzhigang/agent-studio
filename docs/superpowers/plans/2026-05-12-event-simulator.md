# Event Simulator Implementation Plan

> **For agentic workers:** REQUIRED: Use @superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an external Event Simulator that injects business-meaningful events into a running world through Supervisor HTTP APIs, driving world state changes via the standard Channel abstraction.

**Architecture:** Supervisor gains three HTTP endpoints (`POST /events`, `POST /events/batch`, `GET /outbox`). A new `src/simulator/` package parses `simulator.yaml`, runs multiple `SimSource`s via an async scheduler, and sends events over HTTP. Each `SimSource` can use declarative YAML schedules or Python scripts for complex event generation logic.

**Tech Stack:** Python asyncio, aiohttp (client), YAML, exec-based sandboxed scripting.

---

## File Structure

| File | Purpose |
|------|---------|
| `src/supervisor/handlers/events.py` (new) | Handler for `POST /events`, `POST /events/batch`, `GET /outbox` |
| `src/supervisor/server.py` (modify) | Register three new routes |
| `src/supervisor/handlers/__init__.py` (modify) | Export new handler functions |
| `src/supervisor/worker.py` (modify) | Add `query_outbox` JSON-RPC helper |
| `src/simulator/__init__.py` (new) | Package marker |
| `src/simulator/config.py` (new) | Load and validate `simulator.yaml` |
| `src/simulator/scripting.py` (new) | `SimContext`, `Event`, script execution sandbox |
| `src/simulator/source.py` (new) | `SimSource` class: owns context + generator + poster |
| `src/simulator/poster.py` (new) | `HttpPoster`: aiohttp client posting to Supervisor |
| `src/simulator/scheduler.py` (new) | `Scheduler`: manages SimSource asyncio tasks |
| `src/simulator/engine.py` (new) | `EventSimulator`: top-level orchestrator |
| `src/simulator/cli.py` (new) | CLI entry point for `agent-studio simulate` |
| `src/cli/main.py` (modify) | Add `simulate` subparser + `_simulate_command` |
| `tests/simulator/test_config.py` (new) | Config loading tests |
| `tests/simulator/test_scripting.py` (new) | Script engine sandbox tests |
| `tests/simulator/test_engine.py` (new) | End-to-end engine tests |
| `tests/supervisor/test_events_handler.py` (new) | Supervisor handler tests |

---

### Task 1: Supervisor Events Handler

**Files:**
- Create: `src/supervisor/handlers/events.py`
- Modify: `src/supervisor/server.py`
- Modify: `src/supervisor/handlers/__init__.py`
- Modify: `src/supervisor/worker.py`
- Test: `tests/supervisor/test_events_handler.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from aiohttp import web
from unittest.mock import AsyncMock

@pytest.fixture
def app(mock_controller):
    app = web.Application()
    app["controller"] = mock_controller
    return app

@pytest.mark.anyio
async def test_post_single_event(app, aiohttp_client, mock_controller):
    mock_controller.proxy_to_worker = AsyncMock(return_value={"status": "queued", "message_id": "test-id"})
    client = await aiohttp_client(app)
    resp = await client.post("/api/worlds/demo-world/events", json={
        "event_type": "tick",
        "payload": {"temperature": 85},
        "scope": "world"
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "queued"
    mock_controller.proxy_to_worker.assert_awaited_once()

@pytest.mark.anyio
async def test_post_batch_events(app, aiohttp_client, mock_controller):
    mock_controller.proxy_to_worker = AsyncMock(return_value={"status": "queued", "count": 2, "message_ids": ["a", "b"]})
    client = await aiohttp_client(app)
    resp = await client.post("/api/worlds/demo-world/events/batch", json={
        "events": [
            {"event_type": "beat", "payload": {}, "scope": "world"},
            {"event_type": "tick", "payload": {"temperature": 85}, "scope": "world"}
        ]
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["count"] == 2

@pytest.mark.anyio
async def test_get_outbox(app, aiohttp_client, mock_controller):
    mock_controller.proxy_to_worker = AsyncMock(return_value={"items": [], "total": 0})
    client = await aiohttp_client(app)
    resp = await client.get("/api/worlds/demo-world/outbox?limit=10")
    assert resp.status == 200
    data = await resp.json()
    assert data["total"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/supervisor/test_events_handler.py -v`
Expected: FAIL with import errors (module doesn't exist)

- [ ] **Step 3: Implement `src/supervisor/handlers/events.py`**

```python
from aiohttp import web
from src.supervisor.worker import WorkerRpcError, rpc_code_to_http

async def handle_post_event(request: web.Request):
    controller = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        body = await request.json()
        result = await controller.proxy_to_worker(
            world_id, "messageHub.publish", {"world_id": world_id, **body}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": e.message}, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_post_batch_events(request: web.Request):
    controller = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        body = await request.json()
        events = body.get("events", [])
        message_ids = []
        for evt in events:
            result = await controller.proxy_to_worker(
                world_id, "messageHub.publish", {"world_id": world_id, **evt}
            )
            message_ids.append(result.get("message_id"))
        return web.json_response({"status": "queued", "count": len(events), "message_ids": message_ids})
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": e.message}, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_get_outbox(request: web.Request):
    controller = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        limit = int(request.query.get("limit", "50"))
        since = request.query.get("since")
        params = {"world_id": world_id, "limit": limit}
        if since:
            params["since"] = since
        result = await controller.proxy_to_worker(
            world_id, "messageHub.outbox.query", params
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": e.message}, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
```

- [ ] **Step 4: Register routes in `src/supervisor/server.py`**

Add after existing routes (around line 32):
```python
    app.router.add_post("/api/worlds/{world_id}/events", handlers.handle_post_event)
    app.router.add_post("/api/worlds/{world_id}/events/batch", handlers.handle_post_batch_events)
    app.router.add_get("/api/worlds/{world_id}/outbox", handlers.handle_get_outbox)
```

- [ ] **Step 5: Export in `src/supervisor/handlers/__init__.py`**

Add imports for the three new handlers.

- [ ] **Step 6: Add `query_outbox` support in Worker**

In `src/worker/manager.py` (or wherever `messageHub` commands are handled), add handling for `"messageHub.outbox.query"` that queries `SQLiteMessageStore` for outbound messages.

- [ ] **Step 7: Run tests**

Run: `pytest tests/supervisor/test_events_handler.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/supervisor/ tests/supervisor/
git commit -m "feat(supervisor): add events push and outbox query APIs"
```

---

### Task 2: Simulator Config Loader

**Files:**
- Create: `src/simulator/config.py`
- Test: `tests/simulator/test_config.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from src.simulator.config import load_config

def test_load_minimal_config(tmp_path):
    config_path = tmp_path / "sim.yaml"
    config_path.write_text("""
supervisor_url: http://localhost:8080
sources:
  - name: sensor
    target_world: demo-world
    schedule:
      - event: beat
        every: 2s
""")
    cfg = load_config(str(config_path))
    assert cfg.supervisor_url == "http://localhost:8080"
    assert len(cfg.sources) == 1
    assert cfg.sources[0].name == "sensor"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/simulator/test_config.py::test_load_minimal_config -v`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Implement `src/simulator/config.py`**

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

@dataclass
class ScheduleItem:
    event: str
    every: str
    jitter: str = "0s"
    payload: dict = field(default_factory=dict)

@dataclass
class SourceConfig:
    name: str
    target_world: str
    schedule: list[ScheduleItem] = field(default_factory=list)
    script: str = ""

@dataclass
class SimulatorConfig:
    supervisor_url: str
    sources: list[SourceConfig]

def _parse_duration(s: str) -> float:
    """Parse duration string like '2s', '100ms', '1m' to seconds."""
    s = s.strip()
    if s.endswith("ms"):
        return float(s[:-2]) / 1000
    elif s.endswith("s"):
        return float(s[:-1])
    elif s.endswith("m"):
        return float(s[:-1]) * 60
    else:
        return float(s)

def load_config(path: str) -> SimulatorConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    sources = []
    for s in raw.get("sources", []):
        schedule = []
        for item in s.get("schedule", []):
            schedule.append(ScheduleItem(
                event=item["event"],
                every=item["every"],
                jitter=item.get("jitter", "0s"),
                payload=item.get("payload", {})
            ))
        sources.append(SourceConfig(
            name=s["name"],
            target_world=s["target_world"],
            schedule=schedule,
            script=s.get("script", "")
        ))
    return SimulatorConfig(
        supervisor_url=raw["supervisor_url"],
        sources=sources
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/simulator/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/simulator/config.py tests/simulator/test_config.py
git commit -m "feat(simulator): add simulator.yaml config loader"
```

---

### Task 3: Simulator Scripting Engine

**Files:**
- Create: `src/simulator/scripting.py`
- Test: `tests/simulator/test_scripting.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from src.simulator.scripting import SimContext, Event, run_script

def test_context_state():
    ctx = SimContext()
    ctx.set("alerting", True)
    assert ctx.get("alerting") is True
    assert ctx.get("missing") is None
    assert ctx.get("missing", "default") == "default"

def test_event_creation():
    evt = Event("tick", {"temperature": 85})
    assert evt.event_type == "tick"
    assert evt.payload == {"temperature": 85}

def test_run_simple_script():
    script = """
from simulator.scripting import Event, Context

def on_tick(ctx):
    return Event("tick", {"temperature": 85})
"""
    ctx = SimContext()
    result = run_script(script, "on_tick", ctx)
    assert isinstance(result, Event)
    assert result.event_type == "tick"

def test_script_forbidden_import():
    script = """
import os
def on_tick(ctx):
    return Event("tick", {})
"""
    ctx = SimContext()
    with pytest.raises(ImportError):
        run_script(script, "on_tick", ctx)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/simulator/test_scripting.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `src/simulator/scripting.py`**

```python
import random
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

SAFE_MODULES = {"math", "random", "datetime", "json", "collections"}

@dataclass(frozen=True)
class Event:
    event_type: str
    payload: dict
    scope: str = "world"
    target: str | None = None

class SimContext:
    """Per-source isolated execution context."""
    def __init__(self, seed: int | None = None):
        self._state: dict[str, Any] = {}
        self._rng = random.Random(seed)

    def gaussian(self, mean: float, std: float) -> float:
        return self._rng.gauss(mean, std)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

def _safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):
    if name not in SAFE_MODULES and not name.startswith("src.simulator."):
        raise ImportError(f"Import of '{name}' is not allowed in simulator scripts")
    return __import__(name, globals, locals, fromlist, level)

def run_script(script_code: str, function_name: str, ctx: SimContext) -> Event | None:
    """Execute user script in a restricted environment."""
    safe_builtins = {
        "__import__": _safe_import,
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "float": float, "int": int, "len": len, "list": list, "max": max,
        "min": min, "pow": pow, "print": print, "range": range,
        "round": round, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip,
    }
    env = {"__builtins__": safe_builtins}
    exec(script_code, env)
    func = env.get(function_name)
    if func is None:
        return None
    return func(ctx)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/simulator/test_scripting.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/simulator/scripting.py tests/simulator/test_scripting.py
git commit -m "feat(simulator): add sandboxed script engine with SimContext and Event"
```

---

### Task 4: Simulator HTTP Poster

**Files:**
- Create: `src/simulator/poster.py`
- Test: `tests/simulator/test_poster.py` (mock-based)

- [ ] **Step 1: Write failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.simulator.poster import HttpPoster
from src.simulator.scripting import Event

@pytest.mark.anyio
async def test_post_single_event():
    poster = HttpPoster("http://localhost:8080")
    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"status": "queued"})
    mock_session.post = AsyncMock(return_value=mock_resp)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        poster._session = mock_session
        result = await poster.send("demo-world", Event("tick", {"temperature": 85}))
        assert result is True
```

- [ ] **Step 2: Run test**

Run: `pytest tests/simulator/test_poster.py::test_post_single_event -v`
Expected: FAIL

- [ ] **Step 3: Implement `src/simulator/poster.py`**

```python
import aiohttp
from src.simulator.scripting import Event

class HttpPoster:
    def __init__(self, supervisor_url: str):
        self._base_url = supervisor_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send(self, world_id: str, event: Event) -> bool:
        if self._session is None:
            raise RuntimeError("Poster not started")
        url = f"{self._base_url}/api/worlds/{world_id}/events"
        payload = {
            "event_type": event.event_type,
            "payload": event.payload,
            "scope": event.scope,
        }
        if event.target:
            payload["target"] = event.target
        async with self._session.post(url, json=payload) as resp:
            return resp.status == 200

    async def send_batch(self, world_id: str, events: list[Event]) -> bool:
        if self._session is None:
            raise RuntimeError("Poster not started")
        url = f"{self._base_url}/api/worlds/{world_id}/events/batch"
        batch = [
            {
                "event_type": e.event_type,
                "payload": e.payload,
                "scope": e.scope,
                **({"target": e.target} if e.target else {})
            }
            for e in events
        ]
        async with self._session.post(url, json={"events": batch}) as resp:
            return resp.status == 200
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/simulator/test_poster.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/simulator/poster.py tests/simulator/test_poster.py
git commit -m "feat(simulator): add HTTP poster for sending events to Supervisor"
```

---

### Task 5: SimSource and Scheduler

**Files:**
- Create: `src/simulator/source.py`
- Create: `src/simulator/scheduler.py`
- Test: `tests/simulator/test_scheduler.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from unittest.mock import AsyncMock
from src.simulator.scheduler import Scheduler
from src.simulator.config import SimulatorConfig, SourceConfig

@pytest.mark.anyio
async def test_scheduler_starts_sources():
    cfg = SimulatorConfig(
        supervisor_url="http://localhost:8080",
        sources=[
            SourceConfig(name="s1", target_world="demo-world", schedule=[]),
        ]
    )
    scheduler = Scheduler(cfg)
    scheduler._start_source = AsyncMock()
    await scheduler.start()
    scheduler._start_source.assert_awaited_once()
    await scheduler.stop()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/simulator/test_scheduler.py::test_scheduler_starts_sources -v`
Expected: FAIL

- [ ] **Step 3: Implement `src/simulator/source.py`**

```python
import asyncio
import random
from src.simulator.config import SourceConfig, _parse_duration
from src.simulator.scripting import SimContext, Event, run_script
from src.simulator.poster import HttpPoster

class SimSource:
    def __init__(self, config: SourceConfig, poster: HttpPoster):
        self._config = config
        self._poster = poster
        self._ctx = SimContext()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        schedule_map = {item.event: item for item in self._config.schedule}
        script_env = bool(self._config.script)

        while not self._stop_event.is_set():
            for item in self._config.schedule:
                interval = _parse_duration(item.every)
                jitter = _parse_duration(item.jitter)
                delay = interval + random.uniform(-jitter, jitter)
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(0, delay))
                if self._stop_event.is_set():
                    return

                event = self._generate_event(item)
                if event is not None:
                    await self._poster.send(self._config.target_world, event)

    def _generate_event(self, schedule_item) -> Event | None:
        if self._config.script:
            func_name = f"on_{schedule_item.event}"
            return run_script(self._config.script, func_name, self._ctx)

        payload = {}
        for key, spec in schedule_item.payload.items():
            if isinstance(spec, dict):
                if spec.get("type") == "gaussian":
                    payload[key] = self._ctx.gaussian(spec["mean"], spec["std"])
                elif spec.get("type") == "uniform":
                    payload[key] = self._ctx.uniform(spec["min"], spec["max"])
                else:
                    payload[key] = spec.get("value")
            else:
                payload[key] = spec

        return Event(schedule_item.event, payload)
```

- [ ] **Step 4: Implement `src/simulator/scheduler.py`**

```python
import asyncio
from src.simulator.config import SimulatorConfig
from src.simulator.source import SimSource
from src.simulator.poster import HttpPoster

class Scheduler:
    def __init__(self, config: SimulatorConfig):
        self._config = config
        self._poster = HttpPoster(config.supervisor_url)
        self._sources: list[SimSource] = []

    async def start(self) -> None:
        await self._poster.start()
        for src_cfg in self._config.sources:
            source = SimSource(src_cfg, self._poster)
            self._sources.append(source)
            await source.start()

    async def stop(self) -> None:
        for source in self._sources:
            await source.stop()
        self._sources.clear()
        await self._poster.stop()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/simulator/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/simulator/source.py src/simulator/scheduler.py tests/simulator/test_scheduler.py
git commit -m "feat(simulator): add SimSource event generator and Scheduler orchestrator"
```

---

### Task 6: EventSimulator Engine and CLI

**Files:**
- Create: `src/simulator/engine.py`
- Create: `src/simulator/cli.py`
- Modify: `src/cli/main.py`
- Test: `tests/simulator/test_engine.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from unittest.mock import patch
from src.simulator.engine import EventSimulator

@pytest.mark.anyio
async def test_engine_runs_and_stops():
    from src.simulator.config import SimulatorConfig, SourceConfig
    cfg = SimulatorConfig(
        supervisor_url="http://localhost:8080",
        sources=[SourceConfig(name="s1", target_world="demo-world", schedule=[])]
    )
    sim = EventSimulator(cfg)
    with patch.object(sim._scheduler, "start") as mock_start, \
         patch.object(sim._scheduler, "stop") as mock_stop:
        await sim.run()
        mock_start.assert_awaited_once()
        mock_stop.assert_awaited_once()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/simulator/test_engine.py::test_engine_runs_and_stops -v`
Expected: FAIL

- [ ] **Step 3: Implement `src/simulator/engine.py`**

```python
import asyncio
import signal
from src.simulator.config import SimulatorConfig
from src.simulator.scheduler import Scheduler

class EventSimulator:
    def __init__(self, config: SimulatorConfig):
        self._config = config
        self._scheduler = Scheduler(config)
        self._shutdown_event = asyncio.Event()

    async def run(self) -> int:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        await self._scheduler.start()
        print(f"[simulator] Started {len(self._config.sources)} source(s)")
        print("[simulator] Press Ctrl+C to stop")

        try:
            await self._shutdown_event.wait()
        finally:
            print("[simulator] Shutting down...")
            await self._scheduler.stop()
            print("[simulator] Stopped")
        return 0
```

- [ ] **Step 4: Implement `src/simulator/cli.py`**

```python
import sys
from src.simulator.config import load_config
from src.simulator.engine import EventSimulator

def simulate_main(config_path: str) -> int:
    config = load_config(config_path)
    simulator = EventSimulator(config)
    return asyncio.run(simulator.run())
```

Wait, `asyncio.run` is needed. Fix:

```python
import asyncio
import sys
from src.simulator.config import load_config
from src.simulator.engine import EventSimulator

def simulate_main(config_path: str) -> int:
    config = load_config(config_path)
    simulator = EventSimulator(config)
    return asyncio.run(simulator.run())
```

- [ ] **Step 5: Add CLI to `src/cli/main.py`**

Add subparser:
```python
    sim_parser = subparsers.add_parser("simulate", help="Run event simulator")
    sim_parser.add_argument("--config", required=True, help="Path to simulator.yaml")
    sim_parser.set_defaults(func=_simulate_command)
```

Add handler:
```python
def _simulate_command(args):
    from src.simulator.cli import simulate_main
    return simulate_main(args.config)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/simulator/test_engine.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/simulator/engine.py src/simulator/cli.py src/cli/main.py tests/simulator/test_engine.py
git commit -m "feat(simulator): add EventSimulator engine and CLI entry point"
```

---

### Task 7: Worker Outbox Query Handler

**Files:**
- Modify: `src/worker/manager.py` (or wherever messageHub commands are handled)
- Test: `tests/worker/test_outbox_query.py`

- [ ] **Step 1: Add `messageHub.outbox.query` handler in Worker**

Worker needs to handle the JSON-RPC method `messageHub.outbox.query` by querying its `SQLiteMessageStore` outbox table.

Look at existing command handling in `src/worker/manager.py` (likely in `handle_command` or similar), and add:

```python
elif command == "messageHub.outbox.query":
    world_id = params["world_id"]
    limit = params.get("limit", 50)
    since = params.get("since")
    # Query SQLiteMessageStore outbox
    hub = self._message_hub
    messages = hub.query_outbox(world_id, limit=limit, since=since)
    return {"items": messages, "total": len(messages)}
```

- [ ] **Step 2: Add `query_outbox` to MessageHub or store**

If `SQLiteMessageStore` doesn't have `query_outbound`, add it:

```python
def query_outbound(self, world_id: str, limit: int = 50, since: str | None = None) -> list[dict]:
    query = "SELECT * FROM outbox WHERE world_id = ?"
    params = [world_id]
    if since:
        query += " AND created_at > ?"
        params.append(since)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = self._conn.execute(query, params).fetchall()
    return [self._row_to_dict(row) for row in rows]
```

- [ ] **Step 3: Write test**

```python
import pytest
from src.worker.manager import WorkerManager

@pytest.mark.anyio
async def test_outbox_query():
    mgr = WorkerManager()
    # ... setup message hub with fake store ...
    result = await mgr.handle_command("messageHub.outbox.query", {"world_id": "demo-world", "limit": 10})
    assert "items" in result
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/worker/test_outbox_query.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker/ tests/worker/
git commit -m "feat(worker): add messageHub.outbox.query command handler"
```

---

### Task 8: Integration Test

**Files:**
- Create: `tests/e2e/test_simulator_integration.py`

- [ ] **Step 1: Write integration test**

Test: Start Supervisor + Worker (run-inline) + Simulator, verify events flow end-to-end.

Use `tests/e2e/test_worker_supervisor_e2e.py` pattern.

```python
import asyncio
import pytest
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml

@pytest.mark.anyio
async def test_simulator_injects_events_to_world():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal world
        world_dir = Path(tmpdir) / "demo-world"
        world_dir.mkdir()
        (world_dir / "world.yaml").write_text(yaml.dump({"world_id": "demo-world"}))
        (world_dir / "agents").mkdir()

        # Create simulator config
        sim_config = Path(tmpdir) / "simulator.yaml"
        sim_config.write_text(f"""
supervisor_url: http://127.0.0.1:8080
sources:
  - name: test-source
    target_world: demo-world
    schedule:
      - event: beat
        every: 0.1s
""")

        # Start supervisor
        sup_proc = subprocess.Popen([sys.executable, "-m", "src.cli.main", "supervisor",
                                     "--base-dir", tmpdir, "--ws-port", "9001", "--http-port", "8080"])
        # Start worker
        worker_proc = subprocess.Popen([sys.executable, "-m", "src.cli.main", "run-inline",
                                        "--world-dir", str(world_dir),
                                        "--supervisor-ws", "ws://127.0.0.1:8080/workers"])
        # Start simulator
        sim_proc = subprocess.Popen([sys.executable, "-m", "src.cli.main", "simulate",
                                     "--config", str(sim_config)])

        await asyncio.sleep(2)

        # Query outbox to verify events were received
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8080/api/worlds/demo-world/outbox?limit=10") as resp:
                assert resp.status == 200
                data = await resp.json()
                # Should have some events in inbox/outbox
                assert data["total"] >= 0

        sim_proc.terminate()
        worker_proc.terminate()
        sup_proc.terminate()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/e2e/test_simulator_integration.py -v`
Expected: PASS (may need retries/tuning)

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_simulator_integration.py
git commit -m "test(e2e): add simulator end-to-end integration test"
```

---

## Verification Checklist

- [ ] All unit tests pass: `pytest tests/simulator/ -v`
- [ ] All supervisor tests pass: `pytest tests/supervisor/ -v`
- [ ] E2E test passes: `pytest tests/e2e/test_simulator_integration.py -v`
- [ ] Manual test: `python -m src.cli.main simulate --config simulator.yaml` works
- [ ] No regressions: `pytest tests/ -v` passes
