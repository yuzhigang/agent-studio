from src.worker.server.jsonrpc_ws import JsonRpcError


async def message_hub_publish(manager, bundle, params):
    hub = manager._message_hub
    if hub is None:
        raise JsonRpcError(-32102, "message hub not initialized")
    hub.on_inbound(manager._message_envelope_from_params(params))
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
