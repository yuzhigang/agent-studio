import json


class JsonRpcConnection:
    def __init__(self, websocket):
        self._ws = websocket
        self._handlers = {}

    def register(self, method: str, handler):
        self._handlers[method] = handler

    def parse_message(self, raw: str) -> dict:
        return json.loads(raw)

    def build_response(self, req_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def build_error(self, req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def build_notification(self, method: str, params: dict) -> dict:
        return {"jsonrpc": "2.0", "method": method, "params": params}

    async def handle_message(self, raw: str) -> dict | None:
        msg = self.parse_message(raw)
        if "method" not in msg:
            return None
        method = msg["method"]
        req_id = msg.get("id")
        params = msg.get("params", {})
        handler = self._handlers.get(method)
        if handler is None:
            if req_id is not None:
                return self.build_error(req_id, -32601, f"Method not found: {method}")
            return None
        try:
            result = await handler(params, req_id)
            if req_id is not None and result is not None:
                return self.build_response(req_id, result)
        except JsonRpcError as e:
            if req_id is not None:
                return self.build_error(req_id, e.code, e.message)
        except Exception as e:
            if req_id is not None:
                return self.build_error(req_id, -32603, str(e))
        return None

    async def send(self, msg: dict):
        if self._ws is not None and not self._ws.closed:
            await self._ws.send(json.dumps(msg))

    async def close(self):
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
