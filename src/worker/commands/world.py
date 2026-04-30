import asyncio
import os

from src.runtime.world_registry import WorldRegistry
from src.worker.server.jsonrpc_ws import JsonRpcError


async def world_stop(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    force = params.get("force_stop_on_shutdown")
    await manager._graceful_shutdown(bundle, force_stop_on_shutdown=force, permanent=False)
    return {"status": "stopped"}


async def world_remove(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    force = params.get("force_stop_on_shutdown")
    await manager._graceful_shutdown(bundle, force_stop_on_shutdown=force, permanent=True)
    manager.worlds.pop(world_id, None)
    return {"status": "removed"}


async def world_checkpoint(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    await asyncio.to_thread(bundle["state_manager"].checkpoint_world, world_id)
    return {"status": "checkpointed"}


async def world_get_status(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    return {
        "world_id": world_id,
        "loaded": True,
        "status": bundle.get("runtime_status", "running"),
        "scenes": [s["scene_id"] for s in bundle["scene_manager"].list_by_world(world_id)],
    }


async def world_start(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is not None:
        if bundle.get("runtime_status", "running") == "running":
            return {"status": "already_running"}
        manager._bind_world_bundle(world_id, bundle)
        manager._start_shared_scenes_for_bundle(bundle)
        state_mgr = bundle.get("state_manager")
        if state_mgr is not None and state_mgr._task is None:
            await state_mgr.start_async()
        bundle["runtime_status"] = "running"
        return {"status": "started"}
    world_dir = params.get("world_dir")
    if world_dir is None:
        raise JsonRpcError(-32602, "world_dir required for world.start")
    base_dir = os.path.dirname(os.path.abspath(world_dir))
    registry = WorldRegistry(base_dir=base_dir)
    new_bundle = await asyncio.to_thread(registry.load_world, world_id)
    manager.worlds[world_id] = new_bundle
    manager._bind_world_bundle(world_id, new_bundle)
    manager._start_shared_scenes_for_bundle(new_bundle)
    state_mgr = new_bundle.get("state_manager")
    if state_mgr is not None and state_mgr._task is None:
        await state_mgr.start_async()
    new_bundle["runtime_status"] = "running"
    return {"status": "started"}


async def world_reload(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    raise JsonRpcError(-32601, "world.reload not yet implemented")
