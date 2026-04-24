import asyncio
import json
import os
import signal
import sys
import uuid
from datetime import datetime, timezone

from src.runtime.message_hub import MessageHub
from src.runtime.world_registry import WorldRegistry
from src.runtime.stores.sqlite_message_store import SQLiteMessageStore
from src.worker.channels.jsonrpc_channel import JsonRpcChannel
from src.worker.manager import WorkerManager
from src.worker.server.jsonrpc_ws import JsonRpcConnection, JsonRpcError


def run_world(base_dir, supervisor_ws=None, ws_port=None, force_stop_on_shutdown=None):
    base_dir = os.path.abspath(base_dir)

    # WorkerManager loads all worlds in the base directory
    worker_manager = WorkerManager()
    world_ids = worker_manager.load_worlds(base_dir)

    # Apply force_stop_on_shutdown override if provided
    if force_stop_on_shutdown is not None:
        for bundle in worker_manager.worlds.values():
            bundle["force_stop_on_shutdown"] = force_stop_on_shutdown

    # Create worker-level MessageHub and register all worlds
    worker_dir = os.path.join(os.path.expanduser("~"), ".agent-studio", "workers", str(os.getpid()))
    msg_store = SQLiteMessageStore(worker_dir)
    channel = JsonRpcChannel(supervisor_ws) if supervisor_ws else None
    message_hub = MessageHub(msg_store, channel)

    for world_id, bundle in worker_manager.worlds.items():
        bus = bundle["event_bus_registry"].get_or_create(world_id)
        message_hub.register_world(world_id, bus, bundle.get("model_events", {}))
        bundle["message_hub"] = message_hub

    # Start shared scenes for all loaded worlds
    for bundle in worker_manager.worlds.values():
        _start_shared_scenes(bundle)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_fut: asyncio.Future | None = None

    # ---- Signal handling ----

    def _on_signal(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_shutdown_all()))

    async def _shutdown_all():
        for world_id in list(worker_manager.worlds.keys()):
            try:
                await worker_manager.handle_command("world.stop", {"world_id": world_id})
            except JsonRpcError as e:
                print(f"Shutdown aborted for {world_id}: {e.message}")
                return
            except Exception:
                pass
        if main_fut is not None and not main_fut.done():
            main_fut.cancel()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    tasks = []

    async def _start_and_run():
        nonlocal main_fut
        await message_hub.start()
        main_fut = asyncio.Future()
        try:
            await main_fut
        finally:
            await message_hub.stop()

    async def _start_state_managers():
        await worker_manager.start_async()

    tasks.append(loop.create_task(_start_and_run()))
    tasks.append(loop.create_task(_start_state_managers()))

    if ws_port is not None:
        # TODO: Worker-level WebSocket server for direct client connections
        pass

    if supervisor_ws is not None:
        tasks.append(loop.create_task(run_supervisor_client(worker_manager, supervisor_ws)))

    try:
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks))
        else:
            loop.run_until_complete(_block_forever())
    finally:
        loop.close()

    return 0


def _start_shared_scenes(bundle):
    store = bundle["store"]
    sm = bundle["scene_manager"]
    world_id = bundle["world_id"]
    scenes = store.list_scenes(world_id)
    for scene_data in scenes:
        if scene_data.get("mode") == "shared":
            scene_id = scene_data["scene_id"]
            refs = scene_data.get("refs", [])
            local_instances = scene_data.get("local_instances", {})
            sm.start(world_id, scene_id, mode="shared", references=refs, local_instances=local_instances)


def _graceful_shutdown(bundle, force_stop_on_shutdown=None):
    world_id = bundle["world_id"]
    sm = bundle["scene_manager"]
    state_mgr = bundle["state_manager"]
    registry = bundle.get("_registry")

    if force_stop_on_shutdown is None:
        force_stop_on_shutdown = bundle.get("force_stop_on_shutdown", False)

    # 1. Stop isolated scenes
    isolated_scenes = [s for s in sm.list_by_world(world_id) if s.get("mode") == "isolated"]
    for scene in isolated_scenes:
        if not force_stop_on_shutdown:
            raise JsonRpcError(-32003, "isolated scenes are running and force_stop_on_shutdown is false")
        sm.stop(world_id, scene["scene_id"])

    # 2. Stop shared scenes
    shared_scenes = [s for s in sm.list_by_world(world_id) if s.get("mode") == "shared"]
    for scene in shared_scenes:
        sm.stop(world_id, scene["scene_id"])

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
    state_mgr.untrack_world(world_id)
    state_mgr.checkpoint_world(world_id)

    # 5. Unload world and release file lock
    if registry is not None:
        registry.unload_world(world_id)


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


# ---------------------------------------------------------------------------
# Supervisor client (module-level export, reused by run_inline)
# ---------------------------------------------------------------------------

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
                    "started_at": datetime.now(timezone.utc).isoformat(),
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
                    await worker_manager.handle_command("world.stop", {"world_id": world_id})
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
                    "instance_count": len(bundle["instance_manager"].list_by_world(world_id)),
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "worlds": worlds_status,
                },
            ))
        except websockets.exceptions.ConnectionClosed:
            break


def _register_worker_handlers(conn: JsonRpcConnection, worker_manager):
    async def world_stop(params, req_id):
        return await worker_manager.handle_command("world.stop", params)

    async def world_checkpoint(params, req_id):
        return await worker_manager.handle_command("world.checkpoint", params)

    async def world_get_status(params, req_id):
        return await worker_manager.handle_command("world.getStatus", params)

    async def scene_start(params, req_id):
        return await worker_manager.handle_command("scene.start", params)

    async def scene_stop(params, req_id):
        return await worker_manager.handle_command("scene.stop", params)

    async def message_hub_publish(params, req_id):
        return await worker_manager.handle_command("messageHub.publish", params)

    async def message_hub_publish_batch(params, req_id):
        return await worker_manager.handle_command("messageHub.publishBatch", params)

    conn.register("world.stop", world_stop)
    conn.register("world.checkpoint", world_checkpoint)
    conn.register("world.getStatus", world_get_status)
    conn.register("scene.start", scene_start)
    conn.register("scene.stop", scene_stop)
    conn.register("messageHub.publish", message_hub_publish)
    conn.register("messageHub.publishBatch", message_hub_publish_batch)


# Legacy: per-bundle handlers for direct WebSocket server
# TODO: remove once _run_ws_server is refactored to worker-level

def _register_runtime_handlers(conn: JsonRpcConnection, bundle: dict):
    world_id = bundle["world_id"]
    sm = bundle["scene_manager"]
    state_mgr = bundle["state_manager"]

    async def world_stop(params, req_id):
        _graceful_shutdown(bundle)
        return {"status": "stopped"}

    async def world_checkpoint(params, req_id):
        lock = state_mgr._get_world_lock(world_id)
        with lock:
            state_mgr.checkpoint_world(world_id)
        return {"status": "checkpointed"}

    async def world_get_status(params, req_id):
        return {
            "world_id": world_id,
            "loaded": True,
            "scenes": [s["scene_id"] for s in sm.list_by_world(world_id)],
        }

    async def scene_start(params, req_id):
        scene_id = params.get("scene_id")
        if scene_id is None:
            raise JsonRpcError(-32602, "scene_id required")
        existing = sm.get(world_id, scene_id)
        if existing is not None:
            return {"status": "already_running"}
        sm.start(world_id, scene_id, mode="isolated")
        return {"status": "started"}

    async def scene_stop(params, req_id):
        scene_id = params.get("scene_id")
        if scene_id is None:
            raise JsonRpcError(-32602, "scene_id required")
        ok = sm.stop(world_id, scene_id)
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
            params.get("scope", "world"),
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
                record.get("scope", "world"),
                record.get("target"),
            )
        return {"acked_ids": [r.get("id") for r in records]}

    conn.register("world.stop", world_stop)
    conn.register("world.checkpoint", world_checkpoint)
    conn.register("world.getStatus", world_get_status)
    conn.register("scene.start", scene_start)
    conn.register("scene.stop", scene_stop)
    conn.register("messageHub.publish", message_hub_publish)
    conn.register("messageHub.publishBatch", message_hub_publish_batch)
