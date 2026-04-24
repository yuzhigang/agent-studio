"""End-to-end test: start Supervisor process, connect Worker via WebSocket, verify full registration + heartbeat flow."""

import asyncio
import json
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import websockets
import yaml


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host, port, timeout=10):
    """Wait until a server is listening on the given port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


@pytest.fixture
def tmp_base_dir():
    """Create a temporary base directory with a minimal world."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        world_dir = base / "test-world-01"
        world_dir.mkdir()
        # Write world.yaml
        world_yaml = world_dir / "world.yaml"
        world_yaml.write_text(yaml.dump({"name": "e2e-test-world", "version": "1.0"}))
        # Create agents dir
        agents_dir = world_dir / "agents"
        agents_dir.mkdir()
        # Create a minimal agent instance so world loading doesn't fail
        agent_dir = agents_dir / "dummy" / "instances"
        agent_dir.mkdir(parents=True)
        instance_yaml = agent_dir / "dummy-01.instance.yaml"
        instance_yaml.write_text(yaml.dump({
            "model": "basic_agent",
            "name": "dummy-01",
            "description": "Minimal test instance",
            "state": {},
            "behaviors": [],
        }))
        yield str(base)


@pytest.mark.anyio
async def test_full_supervisor_worker_flow(tmp_base_dir):
    """End-to-end: start supervisor, connect worker, heartbeat, deactivate, verify HTTP API."""

    ws_port = _find_free_port()
    http_port = _find_free_port()

    sup_proc = subprocess.Popen(
        [
            sys.executable,
            "-m", "src.cli.main",
            "supervisor",
            "--base-dir", tmp_base_dir,
            "--ws-port", str(ws_port),
            "--http-port", str(http_port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for supervisor HTTP to be reachable
        ready = _wait_for_port("127.0.0.1", http_port, timeout=10)
        assert ready, "Supervisor HTTP server did not start in time"

        ws_url = f"ws://127.0.0.1:{http_port}/workers"

        # Phase 1: Connect worker and send activated
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "id": 1,
                "method": "notify.worker.activated",
                "params": {
                    "worker_id": "e2e-worker-01",
                    "session_id": "e2e-sess-01",
                    "world_ids": ["test-world-01"],
                    "metadata": {"host": "e2e-host", "python": sys.version},
                },
            }))

            # We don't expect a direct response for notifications, but wait a bit
            await asyncio.sleep(0.5)

            # Phase 2: Check HTTP /api/workers
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{http_port}/api/workers") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    workers = data.get("workers", [])
                    matching = [w for w in workers if w["worker_id"] == "e2e-worker-01"]
                    assert len(matching) == 1, f"Worker not found in {workers}"
                    assert matching[0]["world_ids"] == ["test-world-01"]
                    assert matching[0]["status"] == "active"

            # Phase 3: Send heartbeat
            await ws.send(json.dumps({
                "id": 2,
                "method": "notify.worker.heartbeat",
                "params": {
                    "worker_id": "e2e-worker-01",
                    "session_id": "e2e-sess-01",
                    "worlds": [{"world_id": "test-world-01", "status": "running", "instance_count": 0}],
                },
            }))

            await asyncio.sleep(0.3)

            # Phase 4: Stop a world via HTTP API
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(f"http://127.0.0.1:{http_port}/api/worlds/test-world-01/stop") as resp:
                    data = await resp.json()
                    # Should either succeed with stop_requested or have no worker handling it
                    assert resp.status in (200, 404, 502)

            # Phase 5: Deactivate worker
            await ws.send(json.dumps({
                "id": 3,
                "method": "notify.worker.deactivated",
                "params": {
                    "worker_id": "e2e-worker-01",
                    "session_id": "e2e-sess-01",
                },
            }))

            await asyncio.sleep(0.5)

            # Verify worker is gone
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{http_port}/api/workers") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    workers = data.get("workers", [])
                    matching = [w for w in workers if w["worker_id"] == "e2e-worker-01"]
                    assert len(matching) == 0, f"Worker should be deregistered: {matching}"

    finally:
        sup_proc.send_signal(signal.SIGTERM)
        try:
            sup_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sup_proc.kill()
            sup_proc.wait()


@pytest.mark.anyio
async def test_run_inline_loopback_registration(tmp_base_dir):
    """End-to-end: start Supervisor, run run-inline with --supervisor-ws loopback."""

    ws_port = _find_free_port()
    http_port = _find_free_port()

    sup_proc = subprocess.Popen(
        [
            sys.executable,
            "-m", "src.cli.main",
            "supervisor",
            "--base-dir", tmp_base_dir,
            "--ws-port", str(ws_port),
            "--http-port", str(http_port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for supervisor HTTP to be reachable
        ready = _wait_for_port("127.0.0.1", http_port, timeout=10)
        assert ready, "Supervisor HTTP server did not start in time"

        supervisor_ws = f"ws://127.0.0.1:{http_port}/workers"
        world_dir = f"{tmp_base_dir}/test-world-01"

        inline_proc = subprocess.Popen(
            [
                sys.executable,
                "-m", "src.cli.main",
                "run-inline",
                "--world-dir", world_dir,
                "--supervisor-ws", supervisor_ws,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Give run-inline time to connect and register
            await asyncio.sleep(1.5)

            # Verify worker is registered via HTTP API
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{http_port}/api/workers") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    workers = data.get("workers", [])
                    assert len(workers) >= 1, f"Expected at least 1 registered worker, got {workers}"
                    # run-inline creates a worker with auto-generated worker_id
                    w = workers[0]
                    assert "test-world-01" in w.get("world_ids", [])
                    assert w["status"] == "active"

            # Give more time for heartbeats to be sent
            await asyncio.sleep(1.0)

            # Worker should still be active (heartbeat keeps it alive)
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{http_port}/api/workers") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    workers = data.get("workers", [])
                    assert len(workers) >= 1, f"Worker should still be registered after heartbeats"

        finally:
            # Kill run-inline process
            inline_proc.send_signal(signal.SIGTERM)
            try:
                inline_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                inline_proc.kill()
                inline_proc.wait()

            await asyncio.sleep(0.5)

            # Verify worker de-registered after shutdown
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{http_port}/api/workers") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    workers = data.get("workers", [])
                    matching = [w for w in workers if "test-world-01" in w.get("world_ids", [])]
                    assert len(matching) == 0, f"Worker should be deregistered after shutdown: {matching}"

    finally:
        sup_proc.send_signal(signal.SIGTERM)
        try:
            sup_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sup_proc.kill()
            sup_proc.wait()
