import asyncio
import json

from aiohttp import web
from src.supervisor import handlers
from src.supervisor.worker import WorkerController


def run_supervisor(base_dir="worlds", ws_port=8001, http_port=8080):
    controller = WorkerController(base_dir=base_dir)
    # Start heartbeat monitor as background task
    asyncio.get_event_loop().create_task(controller.start_heartbeat_monitor())
    app = web.Application()
    app["controller"] = controller
    app["ws_port"] = ws_port
    app["http_port"] = http_port

    # REST API routes
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

    # WebSocket routes
    app.router.add_get("/workers", _handle_worker_ws)
    app.router.add_get("/ws", _handle_client_ws)

    web.run_app(app, host="0.0.0.0", port=http_port)
    return 0


async def _handle_worker_ws(request: web.Request):
    controller: WorkerController = request.app["controller"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    worker_id = None

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)

            # Handle JSON-RPC responses from worker
            if "id" in data and ("result" in data or "error" in data):
                controller._handle_response(data)
                continue

            method = data.get("method")
            params = data.get("params", {})

            if method == "notify.worker.activated":
                worker_id = params.get("worker_id")
                session_id = params.get("session_id")
                world_ids = params.get("world_ids", [])
                metadata = params.get("metadata", {})
                if worker_id and session_id:
                    await controller.register_worker(worker_id, ws, session_id, world_ids, metadata)

            elif method == "notify.worker.heartbeat":
                wid = params.get("worker_id")
                worlds = params.get("worlds", {})
                if wid:
                    await controller.update_heartbeat(wid, worlds)

            elif method == "notify.worker.deactivated":
                wid = params.get("worker_id")
                if wid:
                    await controller.unregister_worker(wid)
                    worker_id = None

        elif msg.type == web.WSMsgType.ERROR:
            break

    if worker_id:
        await controller.unregister_worker(worker_id)
    return ws


async def _handle_client_ws(request: web.Request):
    controller: WorkerController = request.app["controller"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await controller.add_client(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                # Forward client messages to worker if routed
                data = json.loads(msg.data)
                world_id = data.get("params", {}).get("world_id")
                if world_id:
                    await controller.send_to_worker_by_world(world_id, data)
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        await controller.remove_client(ws)
    return ws
