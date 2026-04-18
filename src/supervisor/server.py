import asyncio
import json
import shutil
import subprocess
import sys

from aiohttp import web
from src.supervisor.gateway import SupervisorGateway


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
    gateway = SupervisorGateway(base_dir=base_dir)
    app = web.Application()
    app["gateway"] = gateway
    app["ws_port"] = ws_port
    app["http_port"] = http_port

    app.router.add_post("/api/worlds/{world_id}/start", _handle_start)
    app.router.add_post("/api/worlds/{world_id}/stop", _handle_stop)
    app.router.add_get("/workers", _handle_worker_ws)
    app.router.add_get("/ws", _handle_client_ws)

    web.run_app(app, host="0.0.0.0", port=http_port)
    return 0


async def _handle_start(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    ws_port = request.app["ws_port"]
    world_id = request.match_info["world_id"]
    runtime = gateway.get_runtime(world_id)
    if runtime is not None:
        return web.json_response({"status": "already_running"})

    # Spawn local subprocess
    world_dir = f"{gateway._base_dir}/{world_id}"
    supervisor_ws = f"ws://localhost:{ws_port}/workers"
    cmd = _build_runtime_cmd(world_dir, supervisor_ws)
    subprocess.Popen(cmd)
    return web.json_response({"status": "starting"})


async def _handle_stop(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    world_id = request.match_info["world_id"]
    runtime = gateway.get_runtime(world_id)
    if runtime is None:
        return web.json_response({"error": "not_running"}, status=404)

    ok = await gateway.send_to_runtime(
        world_id,
        {"jsonrpc": "2.0", "id": 1, "method": "world.stop", "params": {}},
    )
    if not ok:
        return web.json_response({"error": "send_failed"}, status=502)
    return web.json_response({"status": "stop_requested"})


async def _handle_worker_ws(request: web.Request):
    gateway: SupervisorGateway = request.app["gateway"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    session_id = None
    world_id = None

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            method = data.get("method")
            params = data.get("params", {})
            if method == "notify.runtimeOnline":
                world_id = params.get("world_id")
                session_id = params.get("session_id")
                if world_id and session_id:
                    await gateway.register_runtime(world_id, ws, session_id)
            elif method == "notify.runtimeOffline":
                if world_id:
                    await gateway.unregister_runtime(world_id)
        elif msg.type == web.WSMsgType.ERROR:
            break

    if world_id:
        await gateway.unregister_runtime(world_id)
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
                world_id = data.get("params", {}).get("world_id")
                if world_id:
                    await gateway.send_to_runtime(world_id, data)
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        await gateway.remove_client(ws)
    return ws
