"""Integration tests for LibContext + Dataset in sandbox environment."""

import pytest

from src.runtime.instance import Instance
from src.runtime.instance_manager import _DictProxy, _wrap_instance
from src.runtime.lib import LibProxy, SandboxExecutor, lib_function, Dataset
from src.runtime.lib.dataset import _ADAPTERS
from src.runtime.lib.registry import LibRegistry


class _MockAdapter:
    """In-memory mock adapter for testing Dataset integration."""

    def __init__(self, cfg: dict):
        self._data = cfg.get("_mock_data", [])

    def query(self, filters: dict, limit: int, offset: int) -> list[dict]:
        results = self._data
        for k, v in filters.items():
            results = [r for r in results if r.get(k) == v]
        return results[offset : offset + limit]

    def get(self, field: str, value) -> dict | None:
        for r in self._data:
            if r.get(field) == value:
                return r
        return None

    def create(self, data: dict) -> dict:
        self._data.append(data.copy())
        return data

    def update(self, field: str, value, data: dict) -> dict:
        for i, r in enumerate(self._data):
            if r.get(field) == value:
                self._data[i].update(data)
                return self._data[i]
        return data

    def delete(self, field: str, value) -> bool:
        orig_len = len(self._data)
        self._data = [r for r in self._data if r.get(field) != value]
        return len(self._data) < orig_len

    def count(self, filters: dict | None) -> int:
        results = self._data
        if filters:
            for k, v in filters.items():
                results = [r for r in results if r.get(k) == v]
        return len(results)


@pytest.fixture
def mock_adapter_registry():
    """Temporarily register the mock adapter type."""
    _ADAPTERS["mock"] = _MockAdapter
    yield
    del _ADAPTERS["mock"]


class MockDao:
    @lib_function(name="getItems", module="dao")
    def get_items(self, args):
        cfg = self._context["this"].bindings.items
        ds = Dataset(cfg)
        return ds.query(args.get("filters", {}), args.get("limit", 50))

    @lib_function(name="getItem", module="dao")
    def get_item(self, args):
        cfg = self._context["this"].bindings.items
        ds = Dataset(cfg)
        return ds.get(args.get("id"))

    @lib_function(name="createItem", module="dao")
    def create_item(self, args):
        cfg = self._context["this"].bindings.items
        ds = Dataset(cfg)
        return ds.create(args.get("data"))


@pytest.fixture
def mock_registry():
    """Registry with MockDao bound methods pre-registered."""
    registry = LibRegistry()
    registry.clear()
    dao = MockDao()
    registry._data["test.dao.getItems"] = dao.get_items
    registry._data["test.dao.getItem"] = dao.get_item
    registry._data["test.dao.createItem"] = dao.create_item
    return registry


def _make_proxy(registry, mock_data, field_map=None):
    """Helper: build LibProxy with LibContext wired to mock data."""
    bindings_cfg = {
        "type": "mock",
        "table": "items",
        "primaryKey": "id",
        "_mock_data": mock_data,
    }
    if field_map:
        bindings_cfg["fieldMap"] = field_map

    instance = Instance(
        instance_id="test-01",
        model_name="test_manager",
        world_id="w1",
        scope="world",
        bindings={"items": bindings_cfg},
    )
    wrapped = _wrap_instance(instance)

    lib_context = {
        "this": wrapped,
        "payload": _DictProxy({}),
        "source": "test",
        "dispatch": lambda *a, **k: None,
        "world_state": _DictProxy({}),
    }
    return LibProxy(default_namespace="test", registry=registry, lib_context=lib_context)


def test_lib_context_dataset_query(mock_adapter_registry, mock_registry):
    """Script in sandbox calls lib.dao.getItems and receives mock data."""
    mock_data = [
        {"id": "S001", "grade": "Q235B", "width": 1200},
        {"id": "S002", "grade": "Q345B", "width": 1500},
    ]
    proxy = _make_proxy(mock_registry, mock_data)

    script = "result = lib.dao.getItems({})"
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})

    assert len(result) == 2
    assert result[0]["id"] == "S001"
    assert result[1]["id"] == "S002"


def test_lib_context_dataset_with_filters(mock_adapter_registry, mock_registry):
    """Dataset filtering works end-to-end through lib calls."""
    mock_data = [
        {"id": "S001", "grade": "Q235B", "width": 1200},
        {"id": "S002", "grade": "Q345B", "width": 1500},
    ]
    proxy = _make_proxy(mock_registry, mock_data)

    script = "result = lib.dao.getItems({'filters': {'grade': 'Q235B'}})"
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})

    assert len(result) == 1
    assert result[0]["grade"] == "Q235B"


def test_lib_context_dataset_fieldmap(mock_adapter_registry, mock_registry):
    """fieldMap auto-mapping reverses external field names to model fields."""
    mock_data = [
        {"slab_no": "S001", "steel_grade": "Q235B"},
        {"slab_no": "S002", "steel_grade": "Q345B"},
    ]
    proxy = _make_proxy(
        mock_registry,
        mock_data,
        field_map={"id": "slab_no", "grade": "steel_grade"},
    )

    script = "result = lib.dao.getItems({})"
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})

    # Returned as model fields, not external fields
    assert result[0]["id"] == "S001"
    assert result[0]["grade"] == "Q235B"
    assert "slab_no" not in result[0]


def test_lib_context_dataset_create(mock_adapter_registry, mock_registry):
    """Dataset create mutates mock store through lib calls."""
    mock_data = []
    proxy = _make_proxy(mock_registry, mock_data)

    script = "result = lib.dao.createItem({'data': {'id': 'S003', 'grade': 'Q235B'}})"
    executor = SandboxExecutor()
    result = executor.execute(script, {"lib": proxy})

    assert result["id"] == "S003"
    assert result["grade"] == "Q235B"
    assert len(mock_data) == 1
