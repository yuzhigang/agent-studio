from aiohttp import web


async def handle_world_scenes(request: web.Request):
    raise NotImplementedError


async def handle_scene_instances(request: web.Request):
    raise NotImplementedError


async def handle_scene_start(request: web.Request):
    raise NotImplementedError


async def handle_scene_stop(request: web.Request):
    raise NotImplementedError
