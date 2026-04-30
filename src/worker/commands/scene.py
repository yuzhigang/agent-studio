import asyncio

from src.worker.server.jsonrpc_ws import JsonRpcError


async def scene_start(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    scene_id = params.get("scene_id")
    if scene_id is None:
        raise JsonRpcError(-32602, "scene_id required")
    existing = bundle["scene_manager"].get(world_id, scene_id)
    if existing is not None:
        return {"status": "already_running"}
    await asyncio.to_thread(bundle["scene_manager"].start, world_id, scene_id, mode="isolated")
    return {"status": "started"}


async def scene_stop(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    scene_id = params.get("scene_id")
    if scene_id is None:
        raise JsonRpcError(-32602, "scene_id required")
    ok = await asyncio.to_thread(bundle["scene_manager"].stop, world_id, scene_id)
    if not ok:
        raise JsonRpcError(-32002, "scene not found")
    return {"status": "stopped"}


async def world_scenes_list(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    sm = bundle["scene_manager"]
    im = bundle["instance_manager"]
    scenes = sm.list_by_world(world_id)
    instances = im.list_by_world(world_id)
    result = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        scope = f"scene:{scene_id}"
        count = sum(1 for inst in instances if inst.scope == scope)
        result.append({
            "scene_id": scene_id,
            "mode": scene.get("mode", "shared"),
            "instance_count": count,
        })
    return {"scenes": result}
