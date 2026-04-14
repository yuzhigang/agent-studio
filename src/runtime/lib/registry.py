import importlib
import importlib.util
import os
import sys
import threading
from pathlib import Path

from src.runtime.lib.decorator import lib_function
from src.runtime.lib.exceptions import LibNotFoundError, LibRegistrationError


class LibRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *, _singleton: bool = False):
        if _singleton:
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._init()
            return cls._instance
        return super().__new__(cls)

    def __init__(self, *, _singleton: bool = False):
        if not _singleton or getattr(self, "_registry", None) is None:
            self._init()

    def _init(self):
        self._registry = {}
        self._rlock = threading.RLock()
        self._agents_root: Path | None = None
        self._loaded_modules: set[str] = set()

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None

    @property
    def _data(self):
        return self._registry

    def clear(self):
        with self._rlock:
            self._registry.clear()
        for mod_name in list(self._loaded_modules):
            sys.modules.pop(mod_name, None)
        self._loaded_modules.clear()

    def scan(self, agents_root: str):
        agents_path = Path(agents_root)
        if not agents_path.exists():
            return
        self._agents_root = agents_path

        with self._rlock:
            self._registry.clear()
            # Handle shared libs directly
            shared_libs = agents_path / "shared" / "libs"
            if shared_libs.exists():
                for py_file in shared_libs.glob("*.py"):
                    self._load_module("shared", py_file)

            # Handle grouped agents: agents/<group>/<agent>/libs/
            for group_dir in agents_path.iterdir():
                if not group_dir.is_dir() or group_dir.name == "shared":
                    continue
                for agent_dir in group_dir.iterdir():
                    if not agent_dir.is_dir():
                        continue
                    libs_dir = agent_dir / "libs"
                    if not libs_dir.exists():
                        continue
                    namespace = agent_dir.name
                    for py_file in libs_dir.glob("*.py"):
                        self._load_module(namespace, py_file)

    def _exec_module(self, namespace: str, py_file: Path):
        module_name = f"_lib_registry_{namespace}_{py_file.stem}"
        if module_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        else:
            module = sys.modules[module_name]
            importlib.reload(module)
        self._loaded_modules.add(module_name)
        return module

    def _register_functions(self, namespace: str, py_file: Path, module):
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            meta = getattr(obj, "_lib_meta", None)
            if meta is None:
                continue
            declared_ns = meta["namespace"]
            if declared_ns != namespace:
                raise LibRegistrationError(
                    f"{py_file}",
                    details=f"namespace mismatch: declared '{declared_ns}' but file is under '{namespace}'"
                )
            key = f"{namespace}.{py_file.stem}.{meta['name']}"
            self._registry[key] = meta["func"]

    def _load_module(self, namespace: str, py_file: Path):
        module = self._exec_module(namespace, py_file)
        self._register_functions(namespace, py_file, module)

    def reload_module(self, py_file_path: str):
        py_file = Path(py_file_path)
        if self._agents_root is None:
            return
        try:
            rel = py_file.relative_to(self._agents_root)
        except ValueError:
            return
        parts = rel.parts
        # Expected: shared/libs/file.py OR <group>/<agent>/libs/file.py
        if len(parts) < 3 or (parts[1] != "libs" and parts[2] != "libs"):
            return
        if parts[0] == "shared" and parts[1] == "libs":
            namespace = "shared"
        else:
            namespace = parts[1]  # agent name

        with self._rlock:
            module = self._exec_module(namespace, py_file)
            self._register_functions(namespace, py_file, module)

    def lookup(self, namespace: str, module: str, name: str):
        key = f"{namespace}.{module}.{name}"
        with self._rlock:
            func = self._registry.get(key)
        if func is None:
            raise LibNotFoundError(key, details="not registered")
        return func
