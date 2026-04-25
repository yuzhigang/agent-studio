import os
import pytest
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError, LibRegistrationError

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def test_registry_scan_uses_group_agent_namespace(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    # logistics/ladle/libs/dispatcher.py now declares namespace="logistics.ladle"
    func = registry.lookup("logistics.ladle", "dispatcher", "getCandidates")
    assert func({"x": 1}) == {"candidates": []}

    # shared/libs/utils.py declares namespace="shared"
    func = registry.lookup("shared", "utils", "uppercase")
    assert func({"text": "hello"}) == {"text": "HELLO"}


def test_registry_lookup_old_namespace_missing(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    # Old namespace "ladle" should no longer exist
    with pytest.raises(LibNotFoundError):
        registry.lookup("ladle", "dispatcher", "getCandidates")


def test_registry_namespace_mismatch_raises():
    reg = LibRegistry()
    agents_dir = os.path.join(FIXTURES, "agents_bad_namespace")
    with pytest.raises(LibRegistrationError):
        reg.scan(agents_dir)
