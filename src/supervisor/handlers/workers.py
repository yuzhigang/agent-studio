from aiohttp import web
from src.supervisor.worker import WorkerController


async def handle_workers(request: web.Request):
    controller: WorkerController = request.app["controller"]
    workers = []
    for worker in controller._workers.values():
        workers.append({
            "worker_id": worker.worker_id,
            "session_id": worker.session_id,
            "world_ids": worker.world_ids,
            "metadata": worker.metadata,
            "status": worker.status,
        })
    return web.json_response({"items": workers, "total": len(workers)})


async def handle_worker_worlds(request: web.Request):
    controller: WorkerController = request.app["controller"]
    worker_id = request.match_info["worker_id"]
    worker = controller.get_worker(worker_id)
    if worker is None:
        return web.json_response({"error": "worker_not_found", "message": f"Worker '{worker_id}' not found"}, status=404)

    worlds = []
    for world_id in worker.world_ids:
        world_data = controller._world_status_cache.get(world_id, {})
        worlds.append({
            "world_id": world_id,
            "status": world_data.get("status", "unknown"),
            "scene_count": world_data.get("scene_count", 0),
            "instance_count": world_data.get("instance_count", 0),
        })
    return web.json_response({"items": worlds, "total": len(worlds)})
