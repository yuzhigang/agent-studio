import asyncio
import json
import uuid
from typing import Callable

import websockets

from src.runtime.messaging import MessageEnvelope, SendResult
from src.worker.channels.base import Channel
from src.worker.server.jsonrpc_ws import JsonRpcConnection


# RPC error codes that indicate a permanent (non-retryable) failure.
_PERMANENT_RPC_CODES = frozenset({
    -32600,  # Invalid Request
    -32601,  # Method not found
    -32602,  # Invalid params
    -32004,  # World not loaded
    -32102,  # Message hub not initialized
})


class ChannelError(RuntimeError):
    """Transient channel failure (retryable)."""


class PermanentChannelError(RuntimeError):
    """Permanent channel failure (should not be retried)."""


class JsonRpcChannel(Channel):
    def __init__(self, ws_url: str):
        self._url = ws_url
        self._inbound_callback: Callable | None = None
        self._ws: websockets.ClientConnection | None = None
        self._conn: JsonRpcConnection | None = None
        self._ready = False
        self._lock = asyncio.Lock()
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self, inbound_callback: Callable[[MessageEnvelope], None]) -> None:
        self._inbound_callback = inbound_callback
        self._stop_event.clear()
        self._task = asyncio.create_task(self._connect_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            await self._ws.close()
        self._ready = False
        self._task = None
        self._ws = None
        self._conn = None

    def is_ready(self) -> bool:
        return self._ready

    async def send(self, envelope: MessageEnvelope) -> SendResult:
        if not self._ready or self._conn is None:
            return SendResult.RETRYABLE
        req_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "messageHub.publish",
            "params": {
                "message_id": envelope.message_id,
                "source_world": envelope.source_world,
                "target_world": envelope.target_world,
                "event_type": envelope.event_type,
                "payload": envelope.payload,
                "source": envelope.source,
                "scope": envelope.scope,
                "target": envelope.target,
                "trace_id": envelope.trace_id,
                "headers": envelope.headers,
            },
        }
        try:
            result = await self._send_and_wait(req_id, message)
            return (
                SendResult.SUCCESS
                if isinstance(result, dict) and result.get("acked") is True
                else SendResult.RETRYABLE
            )
        except PermanentChannelError:
            return SendResult.PERMANENT
        except ChannelError:
            return SendResult.RETRYABLE
        except Exception:
            return SendResult.RETRYABLE

    async def _connect_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._ws = await websockets.connect(self._url)
                self._conn = JsonRpcConnection(self._ws)
                self._register_handlers()
                async with self._lock:
                    self._ready = True
                while not self._stop_event.is_set():
                    try:
                        raw = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                        if "id" in msg and ("result" in msg or "error" in msg):
                            await self._handle_response(msg)
                            continue
                        resp = await self._conn.handle_message(raw)
                        if resp is not None:
                            await self._conn.send(resp)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break
            except (OSError, websockets.exceptions.WebSocketException):
                pass
            finally:
                async with self._lock:
                    self._ready = False
                self._conn = None
                self._ws = None
            if not self._stop_event.is_set():
                await asyncio.sleep(5)

    def _register_handlers(self) -> None:
        async def on_external_event(params, _req_id):
            if self._inbound_callback is not None:
                self._inbound_callback(
                    MessageEnvelope(
                        message_id=params["message_id"],
                        source_world=params.get("source_world"),
                        target_world=params.get("target_world"),
                        event_type=params["event_type"],
                        payload=params.get("payload", {}),
                        source=params.get("source"),
                        scope=params.get("scope", "world"),
                        target=params.get("target"),
                        trace_id=params.get("trace_id"),
                        headers=params.get("headers") or {},
                    )
                )

        if self._conn is not None:
            self._conn.register("notify.externalEvent", on_external_event)

    async def _send_and_wait(self, req_id: str, message: dict) -> dict:
        if self._conn is None:
            raise ChannelError("connection not ready")
        fut = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = fut
        try:
            await self._conn.send(message)
            return await asyncio.wait_for(fut, timeout=5.0)
        except asyncio.TimeoutError:
            raise ChannelError("timeout waiting for response")
        finally:
            self._pending_requests.pop(req_id, None)

    async def _handle_response(self, data: dict) -> None:
        req_id = data.get("id")
        if req_id is None:
            return
        fut = self._pending_requests.pop(str(req_id), None)
        if fut is not None and not fut.done():
            result = data.get("result", {})
            error = data.get("error")
            if error is not None:
                code = error.get("code", 0)
                msg = error.get("message", "rpc error")
                exc_cls = (
                    PermanentChannelError
                    if code in _PERMANENT_RPC_CODES
                    else ChannelError
                )
                fut.set_exception(exc_cls(f"RPC error {code}: {msg}"))
            else:
                fut.set_result(result)
