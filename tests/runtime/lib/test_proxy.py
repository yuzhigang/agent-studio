import pytest
from src.runtime.lib.proxy import LibProxy
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError


def test_proxy_omit_default_namespace(registry: LibRegistry):
    registry._data["logistics.ladle.dispatcher.getCandidates"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    result = proxy.dispatcher.getCandidates({})
    assert result == {"ok": True}


def test_proxy_shared_namespace(registry: LibRegistry):
    registry._data["shared.data_adapter.transform"] = lambda args: args
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    result = proxy.shared.data_adapter.transform({"x": 1})
    assert result == {"x": 1}


def test_proxy_cross_agent_rejected(registry: LibRegistry):
    registry._data["machines.converter.planner.plan"] = lambda args: args
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    with pytest.raises(LibNotFoundError, match="cross-agent"):
        proxy.machines.converter.planner.plan({})


def test_proxy_full_path_rejected(registry: LibRegistry):
    registry._data["logistics.ladle.dispatcher.getCandidates"] = lambda args: {"ok": True}
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    with pytest.raises(LibNotFoundError, match="cross-agent"):
        proxy.logistics.ladle.dispatcher.getCandidates({})


def test_proxy_missing_raises():
    registry = LibRegistry()
    registry.clear()
    proxy = LibProxy(default_namespace="logistics.ladle", registry=registry)
    with pytest.raises(LibNotFoundError):
        proxy.missing.func({})
