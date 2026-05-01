from aiohttp import web
from src.supervisor.handlers.filters import filter_instances
from src.supervisor.worker import WorkerController, WorkerRpcError, rpc_code_to_http


async def handle_world_instances(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]

    try:
        result = await controller.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instances = result.get("instances", [])

        filtered = filter_instances(
            instances,
            model_id=request.query.get("model_id"),
            scope=request.query.get("scope"),
            lifecycle_state=request.query.get("lifecycle_state"),
            state=request.query.get("state"),
        )

        return web.json_response({"items": filtered, "total": len(filtered)})
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "worker_timeout", "message": "Request to worker timed out"}, status=504)


async def handle_instance_detail(request: web.Request):
    controller: WorkerController = request.app["controller"]
    world_id = request.match_info["world_id"]
    instance_id = request.match_info["instance_id"]

    try:
        result = await controller.proxy_to_worker(
            world_id, "world.instances.get", {"world_id": world_id, "instance_id": instance_id}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "instance_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "worker_timeout", "message": "Request to worker timed out"}, status=504)
