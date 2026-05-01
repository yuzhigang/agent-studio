"""SupervisorConnection — single WebSocket to Supervisor.

Owns the only WebSocket connection from a Worker to Supervisor.
Implements Channel protocol (for MessageHub message routing) and handles
worker lifecycle: registration, heartbeats, command dispatch.

Replaces the previous two-connection design (JsonRpcChannel + run_supervisor_client).
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Callable

import websockets

from src.runtime.messaging import MessageEnvelope, SendResult
from src.worker.channels.base import Channel
from src.worker.channels.jsonrpc_channel import (
    ChannelError,
    PermanentChannelError,
    _PERMANENT_RPC_CODES,
)
from src.worker.server.jsonrpc_ws import JsonRpcConnection


class SupervisorConnection(Channel):
    """Single WebSocket connection from Worker to Supervisor.

    Implements Channel protocol so MessageHub can use it for message routing.
    Also handles worker registration, heartbeats, and command dispatch.
    """

    def __init__(self, ws_url: str, worker_manager):
        self._url = ws_url
        self._wm = worker_manager
        self._ws: websockets.ClientConnection | None = None
        self._conn: JsonRpcConnection | None = None
        self._ready = False
        self._inbound_callback: Callable | None = None
        self._lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Channel protocol
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _connect_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._ws = await websockets.connect(self._url)
                self._conn = JsonRpcConnection(self._ws)
                self._register_all_handlers()
                await self._send_activated()
                async with self._lock:
                    self._ready = True

                # Run recv + heartbeat in parallel; reconnect if either fails
                recv_task = asyncio.create_task(self._recv_loop())
                hb_task = asyncio.create_task(self._heartbeat_loop())
                done, pending = await asyncio.wait(
                    [recv_task, hb_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()

            except (OSError, websockets.exceptions.WebSocketException):
                pass
            finally:
                async with self._lock:
                    self._ready = False
                self._conn = None
                self._ws = None

            if not self._stop_event.is_set():
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Message receive loop
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                msg = json.loads(raw)

                # Handle responses to our own requests (from send())
                if "id" in msg and ("result" in msg or "error" in msg):
                    await self._handle_response(msg)
                    continue

                # Dispatch to registered handlers (commands, external events)
                resp = await self._conn.handle_message(raw)
                if resp is not None:
                    await self._conn.send(resp)

            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                break

    # ------------------------------------------------------------------
    # Heartbeat loop
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(5.0)
            if self._ws is None or self._ws.closed:
                break
            try:
                worlds_status = {}
                for world_id, bundle in self._wm.worlds.items():
                    sm = bundle["scene_manager"]
                    worlds_status[world_id] = {
                        "status": bundle.get("runtime_status", "running"),
                        "scene_count": len(sm.list_by_world(world_id)),
                        "instance_count": len(
                            bundle["instance_manager"].list_by_world(world_id)
                        ),
                        "isolated_scenes": [
                            s["scene_id"]
                            for s in sm.list_by_world(world_id)
                            if s.get("mode") == "isolated"
                        ],
                    }
                await self._conn.send(
                    self._conn.build_notification(
                        "notify.worker.heartbeat",
                        {
                            "worker_id": self._wm.worker_id,
                            "session_id": self._wm.session_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "worlds": worlds_status,
                        },
                    )
                )
            except Exception:
                break

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def _send_activated(self) -> None:
        metadata = {
            "pid": os.getpid(),
            "hostname": (os.uname().nodename if hasattr(os, "uname") else "localhost"),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._conn.send(
            self._conn.build_notification(
                "notify.worker.activated",
                {
                    "worker_id": self._wm.worker_id,
                    "session_id": self._wm.session_id,
                    "world_ids": list(self._wm.worlds.keys()),
                    "metadata": metadata,
                },
            )
        )

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def _register_all_handlers(self) -> None:
        # External event → MessageHub inbound
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

        self._conn.register("notify.externalEvent", on_external_event)

        # Worker commands → WorkerManager.handle_command
        from src.worker.commands import _REGISTRY

        for method in _REGISTRY:

            async def handler(params, req_id, method=method):
                return await self._wm.handle_command(method, params)

            self._conn.register(method, handler)

    # ------------------------------------------------------------------
    # Request / response plumbing
    # ------------------------------------------------------------------

    async def _send_and_wait(self, req_id: str, message: dict) -> dict:
        if self._conn is None:
            raise ChannelError("connection not ready")
        fut = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        try:
            await self._conn.send(message)
            return await asyncio.wait_for(fut, timeout=5.0)
        except asyncio.TimeoutError:
            raise ChannelError("timeout waiting for response")
        finally:
            self._pending.pop(req_id, None)

    async def _handle_response(self, data: dict) -> None:
        req_id = data.get("id")
        if req_id is None:
            return
        fut = self._pending.pop(str(req_id), None)
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
