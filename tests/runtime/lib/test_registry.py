import os
import sys
import pytest
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError, LibRegistrationError

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")

def test_registry_scan_and_lookup(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    func = registry.lookup("ladle", "dispatcher", "getCandidates")
    assert func({"x": 1}) == {"candidates": []}

def test_registry_lookup_missing_raises(registry: LibRegistry):
    with pytest.raises(LibNotFoundError):
        registry.lookup("ladle", "dispatcher", "missing")

def test_registry_namespace_mismatch_raises():
    reg = LibRegistry()
    agents_dir = os.path.join(FIXTURES, "agents_bad_namespace")
    with pytest.raises(LibRegistrationError):
        reg.scan(agents_dir)
