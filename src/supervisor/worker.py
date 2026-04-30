import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


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
                "method": "notify.session.reset",
                "params": {"worker_id": worker_id, "world_ids": world_ids},
            })

    async def unregister_worker(self, worker_id: str):
        async with self._lock:
            worker = self._workers.pop(worker_id, None)
            if worker is not None:
                for wid in worker.world_ids:
                    self._world_to_worker.pop(wid, None)

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

        future = asyncio.get_event_loop().create_future()
        self._pending_requests[req_id] = future

        try:
            ok = await self.send_to_worker(worker.worker_id, message)
            if not ok:
                raise RuntimeError(f"Failed to send request to worker {worker.worker_id}")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            self._pending_requests.pop(req_id, None)

    def _handle_response(self, response: dict) -> None:
        """Handle an incoming JSON-RPC response from a worker."""
        req_id = response.get("id")
        if req_id is None:
            return
        future = self._pending_requests.pop(req_id, None)
        if future is None:
            return
        if "error" in response:
            future.set_exception(RuntimeError(response["error"].get("message", "Unknown error")))
        else:
            future.set_result(response.get("result"))

    async def update_heartbeat(self, worker_id: str):
        worker = self._workers.get(worker_id)
        if worker is not None:
            worker.last_heartbeat = datetime.now(timezone.utc)

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
