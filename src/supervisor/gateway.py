import json
import asyncio


class SupervisorGateway:
    def __init__(self, base_dir: str = "worlds"):
        self._base_dir = base_dir
        self._runtimes: dict[str, tuple] = {}  # world_id -> (ws, session_id)
        self._lock = asyncio.Lock()
        self._clients: list = []  # list of client websockets

    async def register_runtime(self, world_id: str, ws, session_id: str):
        async with self._lock:
            old = self._runtimes.pop(world_id, None)
            if old is not None:
                old_ws, _ = old
                try:
                    await old_ws.close()
                except Exception:
                    pass
            self._runtimes[world_id] = (ws, session_id)
            await self._broadcast(
                {"jsonrpc": "2.0", "method": "notify.sessionReset", "params": {"world_id": world_id}}
            )

    def register_runtime_sync(self, world_id: str, ws, session_id: str):
        # Synchronous wrapper for testing convenience
        old = self._runtimes.pop(world_id, None)
        if old is not None:
            old_ws, _ = old
            try:
                if hasattr(old_ws, 'close') and not getattr(old_ws, 'closed', False):
                    result = old_ws.close()
                    if asyncio.iscoroutine(result):
                        try:
                            asyncio.run(result)
                        except RuntimeError:
                            pass  # event loop already running
            except Exception:
                pass
        self._runtimes[world_id] = (ws, session_id)

    async def unregister_runtime(self, world_id: str):
        async with self._lock:
            self._runtimes.pop(world_id, None)

    def get_runtime(self, world_id: str) -> tuple | None:
        return self._runtimes.get(world_id)

    async def send_to_runtime(self, world_id: str, message: dict) -> bool:
        runtime = self.get_runtime(world_id)
        if runtime is None:
            return False
        ws, _ = runtime
        try:
            if hasattr(ws, 'send_str'):
                await ws.send_str(json.dumps(message))
            else:
                await ws.send(json.dumps(message))
            return True
        except Exception:
            return False

    async def add_client(self, ws):
        self._clients.append(ws)

    async def remove_client(self, ws):
        if ws in self._clients:
            self._clients.remove(ws)

    async def _broadcast(self, message: dict):
        dead = []
        for ws in self._clients:
            try:
                await ws.send_str(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.remove_client(ws)
