from src.worker.server.jsonrpc_ws import JsonRpcError


async def world_instances_list(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    instances = bundle["instance_manager"].list_by_world(world_id)
    return {
        "instances": [
            {
                "id": inst.instance_id,
                "model": inst.model_name,
                "scope": inst.scope,
                "state": inst.state.get("current"),
                "lifecycle_state": inst.lifecycle_state,
                "variables": inst.variables,
                "attributes": inst.attributes,
            }
            for inst in instances
        ]
    }


async def world_instances_get(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    instance_id = params.get("instance_id")
    if instance_id is None:
        raise JsonRpcError(-32602, "instance_id required")
    inst = bundle["instance_manager"].get(world_id, instance_id)
    if inst is None:
        raise JsonRpcError(-32004, f"Instance {instance_id} not found")
    return {
        "instance_id": inst.instance_id,
        "model_name": inst.model_name,
        "scope": inst.scope,
        "state": inst.state,
        "lifecycle_state": inst.lifecycle_state,
        "variables": inst.variables,
        "attributes": inst.attributes,
        "bindings": inst.bindings,
        "links": inst.links,
        "memory": inst.memory,
        "audit": inst.audit,
    }
