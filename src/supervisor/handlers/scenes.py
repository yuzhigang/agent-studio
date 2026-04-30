from aiohttp import web
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
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_scene_instances(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    scene_id = request.match_info["scene_id"]

    try:
        result = await controller.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
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
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


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
