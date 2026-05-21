from src.worker.server.jsonrpc_ws import JsonRpcError


async def message_hub_publish(manager, bundle, params):
    hub = manager._message_hub
    if hub is None:
        raise JsonRpcError(-32102, "message hub not initialized")
    hub.on_inbound(manager._message_envelope_from_params(
        params, default_target_world=params.get("world_id")
    ))
    return {"acked": True}


async def message_hub_publish_batch(manager, bundle, params):
    hub = manager._message_hub
    if hub is None:
        raise JsonRpcError(-32102, "message hub not initialized")
    records = params.get("records", [])
    for record in records:
        hub.on_inbound(
            manager._message_envelope_from_params(
                record,
                default_target_world=params.get("target_world"),
            )
        )
    return {
        "acked_ids": [
            record.get("message_id") or record.get("id")
            for record in records
        ]
    }


async def message_hub_outbox_query(manager, bundle, params):
    hub = manager._message_hub
    if hub is None:
        raise JsonRpcError(-32102, "message hub not initialized")
    world_id = params.get("world_id")
    limit = params.get("limit", 50)
    since = params.get("since")
    messages = hub.query_outbox(world_id, limit=limit, since=since)
    return {"items": messages, "total": len(messages)}
