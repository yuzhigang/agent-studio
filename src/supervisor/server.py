import asyncio
import json
import shutil
import subprocess
import sys
import uuid

from aiohttp import web
from src.supervisor.worker import WorkerController


def _build_runtime_cmd(world_dir: str, supervisor_ws: str) -> list[str]:
    """Build the command to spawn a runtime process.

    Prefer the installed 'agent-studio' CLI entrypoint to keep supervisor
    decoupled from runtime internals. Fallback to invoking the module
    directly when running from source without the script on PATH.
    """
    if shutil.which("agent-studio"):
        return [
            "agent-studio",
            "run",
            f"--world-dir={world_dir}",
            f"--supervisor-ws={supervisor_ws}",
        ]
    return [
        sys.executable,
        "-m",
        "src.cli.main",
        "run",
        f"--world-dir={world_dir}",
        f"--supervisor-ws={supervisor_ws}",
    ]


def run_supervisor(base_dir="worlds", ws_port=8001, http_port=8080):
    gateway = WorkerController(base_dir=base_dir)
    # Start heartbeat monitor as background task
    asyncio.get_event_loop().create_task(gateway.start_heartbeat_monitor())
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = ws_port
    app["http_port"] = http_port

    app.router.add_post("/api/worlds/{world_id}/start", _handle_start)
    app.router.add_post("/api/worlds/{world_id}/stop", _handle_stop)
    app.router.add_get("/api/worlds/{world_id}/instances", _handle_list_instances)
    app.router.add_get("/api/workers", _handle_workers)
    app.router.add_get("/workers", _handle_worker_ws)
    app.router.add_get("/ws", _handle_client_ws)

    web.run_app(app, host="0.0.0.0", port=http_port)
    return 0


async def _handle_start(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    ws_port = request.app["ws_port"]
    world_id = request.match_info["world_id"]
    worker = gateway.get_worker_by_world(world_id)
    if worker is not None:
        return web.json_response({"status": "already_running"})

    # Spawn local subprocess
    world_dir = f"{gateway._base_dir}/{world_id}"
    supervisor_ws = f"ws://localhost:{ws_port}/workers"
    cmd = _build_runtime_cmd(world_dir, supervisor_ws)
    subprocess.Popen(cmd)
    return web.json_response({"status": "starting"})


async def _handle_stop(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    worker = gateway.get_worker_by_world(world_id)
    if worker is None:
        return web.json_response({"error": "not_running"}, status=404)

    ok = await gateway.send_to_worker_by_world(
        world_id,
        {"jsonrpc": "2.0", "id": 1, "method": "world.stop", "params": {"world_id": world_id}},
    )
    if not ok:
        return web.json_response({"error": "send_failed"}, status=502)
    return web.json_response({"status": "stop_requested"})


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


async def _handle_client_ws(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await gateway.add_client(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                # Forward client messages to worker if routed
                data = json.loads(msg.data)
                world_id = data.get("params", {}).get("world_id")
                if world_id:
                    await gateway.send_to_worker_by_world(world_id, data)
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        await gateway.remove_client(ws)
    return ws
