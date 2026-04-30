from aiohttp import web


async def handle_workers(request: web.Request):
    raise NotImplementedError


async def handle_worker_worlds(request: web.Request):
    raise NotImplementedError
