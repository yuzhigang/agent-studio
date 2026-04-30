from aiohttp import web
from src.supervisor.worker import WorkerController, WorkerRpcError, rpc_code_to_http


async def handle_world_models(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]

    try:
        result = await gateway.proxy_to_worker(world_id, "world.models.list", {"world_id": world_id})
        models = result.get("models", [])
        return web.json_response({"items": models, "total": len(models)})
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "world_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)


async def handle_model_detail(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    model_id = request.match_info["model_id"]

    try:
        result = await gateway.proxy_to_worker(
            world_id, "world.models.get", {"world_id": world_id, "model_id": model_id}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "model_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)
