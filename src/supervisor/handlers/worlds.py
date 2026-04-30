from aiohttp import web


async def handle_world_start(request: web.Request):
    raise NotImplementedError


async def handle_world_stop(request: web.Request):
    raise NotImplementedError


async def handle_world_checkpoint(request: web.Request):
    raise NotImplementedError


async def handle_world_detail(request: web.Request):
    raise NotImplementedError
