import pytest
from src.runtime.lib.registry import LibRegistry


@pytest.fixture
def registry():
    reg = LibRegistry()
    yield reg
    reg.clear()
    LibRegistry.reset_instance()


@pytest.fixture
def anyio_backend():
    return "asyncio"
