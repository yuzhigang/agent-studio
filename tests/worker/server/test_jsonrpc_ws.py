import pytest
from src.worker.server.jsonrpc_ws import JsonRpcConnection


def test_parse_request():
    conn = JsonRpcConnection(None)
    req = conn.parse_message('{"jsonrpc": "2.0", "id": 1, "method": "hello", "params": {"a": 1}}')
    assert req["method"] == "hello"
    assert req["id"] == 1


def test_build_response():
    conn = JsonRpcConnection(None)
    resp = conn.build_response(1, {"status": "ok"})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["status"] == "ok"


def test_build_error():
    conn = JsonRpcConnection(None)
    resp = conn.build_error(1, -32001, "locked")
    assert resp["error"]["code"] == -32001
    assert resp["error"]["message"] == "locked"
