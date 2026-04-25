import os
import types
from pathlib import Path

import pytest
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError
from src.runtime.lib.decorator import lib_function

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def test_registry_scan_uses_group_agent_namespace(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    # logistics/ladle/libs/dispatcher.py: @lib_function() on get_candidates
    func = registry.lookup("logistics.ladle", "dispatcher", "get_candidates")
    assert func({"x": 1}) == {"candidates": []}

    # shared/libs/utils.py: @lib_function() on uppercase
    func = registry.lookup("shared", "utils", "uppercase")
    assert func({"text": "hello"}) == {"text": "HELLO"}


def test_registry_lookup_old_namespace_missing(registry: LibRegistry):
    agents_dir = os.path.join(FIXTURES, "agents")
    registry.scan(agents_dir)

    # Old namespace "ladle" should no longer exist
    with pytest.raises(LibNotFoundError):
        registry.lookup("ladle", "dispatcher", "get_candidates")


def test_registry_uses_module_override_in_registration_key(registry: LibRegistry):
    @lib_function(name="getItems", module="dao")
    def get_items(args):
        return {"ok": True}

    module = types.SimpleNamespace(get_items=get_items)
    registry._register_functions("logistics.ladle", Path("fake.py"), module)

    assert registry.lookup("logistics.ladle", "dao", "getItems")({}) == {"ok": True}


def test_reload_module_removes_old_module_override_keys(tmp_path):
    agents_dir = tmp_path / "agents"
    libs_dir = agents_dir / "logistics" / "ladle" / "libs"
    libs_dir.mkdir(parents=True)
    file_path = libs_dir / "adapter.py"
    file_path.write_text(
        "from src.runtime.lib.decorator import lib_function\n"
        "@lib_function(name='getItems', module='dao')\n"
        "def get_items(args):\n"
        "    return {'version': 1}\n",
        encoding="utf-8",
    )

    registry = LibRegistry()
    registry.scan(str(agents_dir))
    assert registry.lookup("logistics.ladle", "dao", "getItems")({}) == {"version": 1}

    file_path.write_text(
        "from src.runtime.lib.decorator import lib_function\n"
        "@lib_function(name='getItems', module='repo')\n"
        "def get_items(args):\n"
        "    return {'version': 2}\n",
        encoding="utf-8",
    )
    registry.reload_module(str(file_path))

    assert registry.lookup("logistics.ladle", "repo", "getItems")({}) == {"version": 2}
    with pytest.raises(LibNotFoundError):
        registry.lookup("logistics.ladle", "dao", "getItems")
