import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class WorkerRpcError(RuntimeError):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


_RPC_ERROR_MAP = {
    -32004: 404,  # World/Scene/Instance not found
    -32003: 409,  # Illegal lifecycle
    -32002: 404,  # Scene not found
    -32001: 409,  # World locked
    -32602: 400,  # Invalid params
    -32601: 501,  # Method not found
}


def rpc_code_to_http(code: int) -> int:
    return _RPC_ERROR_MAP.get(code, 502)


@dataclass
class WorkerState:
    worker_id: str
    session_id: str
    ws: object
    world_ids: list[str]
    metadata: dict = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "active"  # "active" | "unreachable" | "dead"


class WorkerController:
    def __init__(self, base_dir: str = "worlds"):
        self._base_dir = base_dir
        self._workers: dict[str, WorkerState] = {}  # worker_id -> WorkerState
        self._world_to_worker: dict[str, str] = {}  # world_id -> worker_id
        self._clients: list = []  # browser/management client websockets
        self._lock = asyncio.Lock()
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._world_status_cache: dict[str, dict] = {}  # world_id -> latest status from heartbeat
        self._request_counter = 0

    # --- Worker registration ---

    async def register_worker(
        self,
        worker_id: str,
        ws,
        session_id: str,
        world_ids: list[str],
        metadata: dict | None = None,
    ):
        async with self._lock:
            old = self._workers.pop(worker_id, None)
            if old is not None:
                for wid in old.world_ids:
                    self._world_to_worker.pop(wid, None)
                try:
                    await old.ws.close()
                except Exception:
                    pass

            state = WorkerState(
                worker_id=worker_id,
                session_id=session_id,
                ws=ws,
                world_ids=world_ids,
                metadata=metadata or {},
            )
            self._workers[worker_id] = state
            for wid in world_ids:
                self._world_to_worker[wid] = worker_id

            await self._broadcast({
                "jsonrpc": "2.0",
                "method": "notify.worker.activated",
                "params": {
                    "worker_id": worker_id,
                    "session_id": session_id,
                    "world_ids": world_ids,
                    "metadata": metadata or {},
                },
            })

    async def unregister_worker(self, worker_id: str):
        async with self._lock:
            worker = self._workers.pop(worker_id, None)
            if worker is not None:
                for wid in worker.world_ids:
                    self._world_to_worker.pop(wid, None)
                await self._broadcast({
                    "jsonrpc": "2.0",
                    "method": "notify.worker.disconnected",
                    "params": {
                        "worker_id": worker_id,
                        "world_ids": worker.world_ids,
                        "reason": "explicit_deactivation",
                    },
                })

    def get_worker(self, worker_id: str) -> WorkerState | None:
        return self._workers.get(worker_id)

    def get_worker_by_world(self, world_id: str) -> WorkerState | None:
        worker_id = self._world_to_worker.get(world_id)
        if worker_id is None:
            return None
        return self._workers.get(worker_id)

    async def send_to_worker(self, worker_id: str, message: dict) -> bool:
        worker = self.get_worker(worker_id)
        if worker is None:
            return False
        ws = worker.ws
        try:
            if hasattr(ws, "send_str"):
                await ws.send_str(json.dumps(message))
            else:
                await ws.send(json.dumps(message))
            return True
        except Exception:
            return False

    async def send_to_worker_by_world(self, world_id: str, message: dict) -> bool:
        worker = self.get_worker_by_world(world_id)
        if worker is None:
            return False
        return await self.send_to_worker(worker.worker_id, message)

    async def send_request(self, world_id: str, message: dict, timeout: float = 5.0) -> dict:
        """Send a JSON-RPC request to a worker and wait for its response.

        Returns the response result dict. Raises TimeoutError or RuntimeError on failure.
        """
        worker = self.get_worker_by_world(world_id)
        if worker is None:
            raise RuntimeError(f"No worker running world {world_id}")

        # Generate a unique request ID if not present
        req_id = message.get("id")
        if req_id is None:
            req_id = str(uuid.uuid4())
            message = {**message, "id": req_id}

        future = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = future

        try:
            ok = await self.send_to_worker(worker.worker_id, message)
            if not ok:
                raise RuntimeError(f"Failed to send request to worker {worker.worker_id}")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            self._pending_requests.pop(req_id, None)

    async def proxy_to_worker(self, world_id: str, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request to the worker managing world_id and return the result."""
        self._request_counter += 1
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": f"supervisor-{self._request_counter}",
        }
        return await self.send_request(world_id, message)

    def _handle_response(self, response: dict) -> None:
        """Handle an incoming JSON-RPC response from a worker."""
        req_id = response.get("id")
        if req_id is None:
            return
        future = self._pending_requests.pop(req_id, None)
        if future is None:
            return
        if "error" in response:
            error = response["error"]
            future.set_exception(WorkerRpcError(
                error.get("code", 0),
                error.get("message", "Unknown error")
            ))
        else:
            future.set_result(response.get("result"))

    async def update_heartbeat(self, worker_id: str, worlds_status: dict | None = None):
        worker = self._workers.get(worker_id)
        if worker is not None:
            worker.last_heartbeat = datetime.now(timezone.utc)
        if worlds_status:
            for world_id, status in worlds_status.items():
                old = self._world_status_cache.get(world_id, {})
                new_status = status.get("status")
                old_status = old.get("status")
                if new_status != old_status:
                    await self._broadcast({
                        "jsonrpc": "2.0",
                        "method": "notify.world.status_changed",
                        "params": {
                            "world_id": world_id,
                            "status": new_status,
                            "previous_status": old_status,
                            "reason": "heartbeat",
                        },
                    })
                self._world_status_cache[world_id] = status

    # --- Heartbeat monitor ---

    async def start_heartbeat_monitor(self, interval: float = 5.0, timeout: float = 15.0):
        """Periodically check worker heartbeats and mark unreachable ones."""
        while True:
            await asyncio.sleep(interval)
            now = datetime.now(timezone.utc)
            for worker_id, worker in list(self._workers.items()):
                if worker.status == "active" and (now - worker.last_heartbeat).total_seconds() > timeout:
                    worker.status = "unreachable"
                    await self._broadcast({
                        "jsonrpc": "2.0",
                        "method": "notify.worker.disconnected",
                        "params": {
                            "worker_id": worker_id,
                            "world_ids": worker.world_ids,
                            "reason": "heartbeat_timeout",
                        },
                    })

    # --- Client management ---

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
