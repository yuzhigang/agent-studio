from aiohttp import web
from src.supervisor.handlers.filters import filter_instances
from src.supervisor.worker import WorkerController, WorkerRpcError, rpc_code_to_http


async def handle_world_scenes(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]

    try:
        result = await controller.proxy_to_worker(world_id, "world.scenes.list", {"world_id": world_id})
        scenes = result.get("scenes", [])
        return web.json_response({"items": scenes, "total": len(scenes)})
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "worker_timeout", "message": "Request to worker timed out"}, status=504)


async def handle_scene_instances(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]

    try:
        result = await controller.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instances = result.get("instances", [])

        filtered = filter_instances(
            instances,
            model_id=request.query.get("model_id"),
            lifecycle_state=request.query.get("lifecycle_state"),
            state=request.query.get("state"),
            target_scope=f"scene:{scene_id}",
        )

        return web.json_response({"items": filtered, "total": len(filtered)})
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "worker_timeout", "message": "Request to worker timed out"}, status=504)


async def handle_scene_start(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]
    try:
        result = await controller.proxy_to_worker(
            world_id, "scene.start", {"world_id": world_id, "scene_id": scene_id}
        )
        if result.get("status") == "started":
            previous = controller._world_status_cache.get(world_id, {}).get("status")
            await controller._broadcast({
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
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)


async def handle_scene_stop(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]
    try:
        result = await controller.proxy_to_worker(
            world_id, "scene.stop", {"world_id": world_id, "scene_id": scene_id}
        )
        if result.get("status") == "stopped":
            previous = controller._world_status_cache.get(world_id, {}).get("status")
            await controller._broadcast({
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
        status = rpc_code_to_http(e.code)
        if e.code == -32002:
            return web.json_response({"error": "scene_not_found", "message": e.message}, status=status)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
