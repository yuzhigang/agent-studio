from aiohttp import web
from src.supervisor.worker import WorkerRpcError, rpc_code_to_http


async def handle_post_event(request: web.Request):
    controller = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        body = await request.json()
        result = await controller.proxy_to_worker(
            world_id, "messageHub.publish", {"world_id": world_id, **body}
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": e.message}, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_post_batch_events(request: web.Request):
    controller = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        body = await request.json()
        events = body.get("events", [])
        message_ids = []
        for evt in events:
            result = await controller.proxy_to_worker(
                world_id, "messageHub.publish", {"world_id": world_id, **evt}
            )
            message_ids.append(result.get("message_id"))
        return web.json_response({"status": "queued", "count": len(events), "message_ids": message_ids})
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": e.message}, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_get_outbox(request: web.Request):
    controller = request.app["controller"]
    world_id = request.match_info["world_id"]
    try:
        limit = int(request.query.get("limit", "50"))
        since = request.query.get("since")
        params = {"world_id": world_id, "limit": limit}
        if since:
            params["since"] = since
        result = await controller.proxy_to_worker(
            world_id, "messageHub.outbox.query", params
        )
        return web.json_response(result)
    except WorkerRpcError as e:
        status = rpc_code_to_http(e.code)
        return web.json_response({"error": e.message}, status=status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
