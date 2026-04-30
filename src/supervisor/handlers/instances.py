from aiohttp import web
from src.supervisor.worker import WorkerController, WorkerRpcError, rpc_code_to_http


async def handle_world_instances(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]

    try:
        result = await gateway.proxy_to_worker(world_id, "world.instances.list", {"world_id": world_id})
        instances = result.get("instances", [])

        model_id = request.query.get("model_id")
        scope = request.query.get("scope")
        lifecycle_state = request.query.get("lifecycle_state")
        state = request.query.get("state")

        filtered = []
        for inst in instances:
            if model_id and inst.get("model") != model_id:
                continue
            if scope and inst.get("scope") != scope:
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


async def handle_instance_detail(request: web.Request):
    gateway: WorkerController = request.app["gateway"]
    world_id = request.match_info["world_id"]
    instance_id = request.match_info["instance_id"]

    try:
        result = await gateway.proxy_to_worker(
            world_id, "world.instances.get", {"world_id": world_id, "instance_id": instance_id}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": "instance_not_found", "message": e.message}, status=status)
    except TimeoutError:
        return web.json_response({"error": "gateway_timeout"}, status=504)
