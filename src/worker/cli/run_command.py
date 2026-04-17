import asyncio
import json
import os
import signal
import sys
import threading
import uuid

from src.runtime.message_hub import MessageHub
from src.runtime.project_registry import ProjectRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.channels.jsonrpc_channel import JsonRpcChannel
from src.worker.server.jsonrpc_ws import JsonRpcConnection, JsonRpcError


def run_project(project_dir, supervisor_ws=None, ws_port=None, force_stop_on_shutdown=None):
    base_dir = os.path.dirname(os.path.abspath(project_dir))
    project_id = os.path.basename(os.path.abspath(project_dir))

    registry = ProjectRegistry(base_dir=base_dir)
    bundle = registry.load_project(project_id)

    # Apply CLI override or default
    if force_stop_on_shutdown is not None:
        bundle["force_stop_on_shutdown"] = force_stop_on_shutdown

    # Create worker-level MessageHub and register project
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", str(os.getpid()))
    msg_store = SQLiteMessageStore(worker_dir)
    channel = JsonRpcChannel(supervisor_ws) if supervisor_ws else None
    message_hub = MessageHub(msg_store, channel)

    bus = bundle["event_bus_registry"].get_or_create(project_id)
    message_hub.register_project(project_id, bus, bundle.get("model_events", {}))
    bundle["instance_manager"]._message_hub = message_hub
    bundle["message_hub"] = message_hub

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

    async def _start_and_run():
        await message_hub.start()
        try:
            await asyncio.Future()
        finally:
            await message_hub.stop()

    tasks.append(loop.create_task(_start_and_run()))

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

    # 3. Stop MessageHub
    message_hub = bundle.get("message_hub")
    if message_hub is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(message_hub.stop(), loop)
            else:
                loop.run_until_complete(message_hub.stop())
        except Exception:
            pass

    # 4. Untrack and checkpoint
    state_mgr.untrack_project(project_id)
    state_mgr.checkpoint_project(project_id)

    # 5. Unload project and release file lock
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


def _register_supervisor_handlers(conn: JsonRpcConnection, message_hub):
    async def on_external_event(params, _req_id):
        if message_hub is not None:
            message_hub.on_channel_message(
                params.get("event_type", ""),
                params.get("payload", {}),
                params.get("source", ""),
                params.get("scope", "project"),
                params.get("target"),
            )

    conn.register("notify.externalEvent", on_external_event)


async def _run_supervisor_client(bundle, supervisor_ws):
    import websockets

    session_id = str(uuid.uuid4())
    project_id = bundle["project_id"]
    message_hub = bundle.get("message_hub")
    disconnected_at = None

    while True:
        try:
            async with websockets.connect(supervisor_ws) as ws:
                disconnected_at = None
                conn = JsonRpcConnection(ws)
                _register_supervisor_handlers(conn, message_hub)
                # Send runtimeOnline
                await conn.send(
                    conn.build_notification(
                        "notify.runtimeOnline",
                        {"project_id": project_id, "session_id": session_id},
                    )
                )

                # Heartbeat and inbound message loop
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        msg = json.loads(raw)
                        if "id" in msg and ("result" in msg or "error" in msg):
                            continue
                        resp = await conn.handle_message(raw)
                        if resp is not None:
                            await conn.send(resp)
                    except asyncio.TimeoutError:
                        if ws.closed:
                            break
                        await conn.send(
                            conn.build_notification(
                                "notify.heartbeat",
                                {"project_id": project_id, "session_id": session_id},
                            )
                        )
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break
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

    async def message_hub_publish(params, req_id):
        hub = bundle.get("message_hub")
        if hub is None:
            raise JsonRpcError(-32102, "message hub not initialized")
        hub.on_channel_message(
            params.get("event_type", ""),
            params.get("payload", {}),
            params.get("source", ""),
            params.get("scope", "project"),
            params.get("target"),
        )
        return {"acked": True}

    async def message_hub_publish_batch(params, req_id):
        hub = bundle.get("message_hub")
        if hub is None:
            raise JsonRpcError(-32102, "message hub not initialized")
        records = params.get("records", [])
        for record in records:
            hub.on_channel_message(
                record.get("event_type", ""),
                record.get("payload", {}),
                record.get("source", ""),
                record.get("scope", "project"),
                record.get("target"),
            )
        return {"acked_ids": [r.get("id") for r in records]}

    conn.register("project.stop", project_stop)
    conn.register("project.checkpoint", project_checkpoint)
    conn.register("project.getStatus", project_get_status)
    conn.register("scene.start", scene_start)
    conn.register("scene.stop", scene_stop)
    conn.register("messageHub.publish", message_hub_publish)
    conn.register("messageHub.publishBatch", message_hub_publish_batch)
