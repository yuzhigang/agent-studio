from aiohttp import web
from src.supervisor.worker import WorkerController, WorkerRpcError, rpc_code_to_http


async def handle_world_start(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    worker = controller.get_worker_by_world(world_id)
    if worker is not None:
        return web.json_response({"status": "already_running"})

    return web.json_response(
        {"error": "no_worker_available", "message": f"No worker is running world '{world_id}'. Start a worker and connect it to the supervisor."},
        status=503,
    )


async def handle_world_stop(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        result = await controller.proxy_to_worker(world_id, "world.stop", {"world_id": world_id})
        if result.get("status") == "stopped":
            previous = controller._world_status_cache.get(world_id, {}).get("status")
            await controller._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.world.status_changed",
                "params": {
                    "world_id": world_id,
                    "status": "stopped",
                    "previous_status": previous,
                    "reason": "user_request",
                },
            })
            controller._world_status_cache[world_id] = {"status": "stopped"}
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_world_checkpoint(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        result = await controller.proxy_to_worker(world_id, "world.checkpoint", {"world_id": world_id})
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_world_detail(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    worker = controller.get_worker_by_world(world_id)
    if worker is None:
        return web.json_response({"error": "world_not_found"}, status=404)

    try:
        result = await controller.proxy_to_worker(world_id, "world.getStatus", {"world_id": world_id})
        status = result.get("status", "unknown")
        scenes = result.get("scenes", [])

        instances_result = await controller.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instance_count = len(instances_result.get("instances", []))

        return web.json_response({
            "world_id": world_id,
            "worker_id": worker.worker_id,
            "status": status,
            "scenes": scenes,
            "instance_count": instance_count,
        })
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)
