import os
import time
import tempfile
import pytest
from watchdog.observers.polling import PollingObserver
from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.watcher import LibWatcher

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def test_watcher_detects_file_change():
    with tempfile.TemporaryDirectory() as tmpdir:
        ns_dir = os.path.join(tmpdir, "group", "ladle", "libs")
        os.makedirs(ns_dir)
        py_path = os.path.join(ns_dir, "demo.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write('''
from src.runtime.lib.decorator import lib_function
@lib_function(name="demo")
def demo(args: dict) -> dict:
    return {"version": 1}
''')

        registry = LibRegistry()
        registry.clear()
        registry.scan(tmpdir)
        assert registry.lookup("group.ladle", "demo", "demo")({}) == {"version": 1}

        watcher = LibWatcher(tmpdir, registry=registry, observer_class=PollingObserver)
        watcher.start()

        # Modify file
        time.sleep(0.1)
        with open(py_path, "w", encoding="utf-8") as f:
            f.write('''
from src.runtime.lib.decorator import lib_function
@lib_function(name="demo")
def demo(args: dict) -> dict:
    return {"version": 2}
''')

        for _ in range(50):
            if registry.lookup("group.ladle", "demo", "demo")({}) == {"version": 2}:
                break
            time.sleep(0.1)
        else:
            assert False, "hot reload did not occur"
        watcher.stop()
