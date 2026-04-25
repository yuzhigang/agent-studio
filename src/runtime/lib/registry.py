"""LibRegistry: discovers and resolves @lib_function decorated libraries."""

import inspect
import sys
import threading
import types
from pathlib import Path

from src.runtime.agent_namespace import agent_namespace_for_path
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
        self._agents_roots: list[Path] = []
        self._loaded_modules: set[str] = set()
        self._module_keys: dict[str, set[str]] = {}

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
            self._module_keys.clear()
            for mod_name in list(self._loaded_modules):
                sys.modules.pop(mod_name, None)
            self._loaded_modules.clear()

    def scan(self, agents_root: str, *, clear: bool = True):
        agents_path = Path(agents_root)
        if not agents_path.exists():
            return

        with self._rlock:
            if clear:
                self._registry.clear()
                self._module_keys.clear()
                self._agents_roots = []
            if agents_path not in self._agents_roots:
                self._agents_roots.append(agents_path)

            for libs_dir in agents_path.rglob("libs"):
                if not libs_dir.is_dir():
                    continue
                namespace = agent_namespace_for_path(libs_dir, agents_path, "libs")
                if namespace is None:
                    continue
                for py_file in libs_dir.glob("*.py"):
                    self._load_module(namespace, py_file)

    def _exec_module(self, namespace: str, py_file: Path):
        module_name = f"_lib_registry_{namespace}_{py_file.stem}"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
        with open(py_file, "rb") as f:
            code = compile(f.read(), str(py_file), "exec")
        exec(code, module.__dict__)
        self._loaded_modules.add(module_name)
        return module

    def _module_key(self, py_file: Path) -> str:
        return str(py_file.resolve())

    def _registration_parts(self, meta: dict, py_file: Path) -> tuple[str, str]:
        func_name = meta["name"] or meta["entrypoint"]
        mod_name = meta["module"] or py_file.stem
        return mod_name, func_name

    def _register_functions(self, namespace: str, py_file: Path, module):
        class_instances = {}
        registered_keys: set[str] = set()

        for attr_name in dir(module):
            obj = getattr(module, attr_name)

            # 1) 模块级函数
            meta = getattr(obj, "_lib_meta", None)
            if meta is not None:
                mod_name, func_name = self._registration_parts(meta, py_file)
                key = f"{namespace}.{mod_name}.{func_name}"
                self._registry[key] = meta["func"]
                registered_keys.add(key)
                continue

            # 2) 类方法
            if inspect.isclass(obj):
                for method_name in dir(obj):
                    method = getattr(obj, method_name)
                    meta = getattr(method, "_lib_meta", None)
                    if meta is None:
                        continue
                    instance = class_instances.get(attr_name)
                    if instance is None:
                        try:
                            instance = obj()
                        except Exception as e:
                            raise LibRegistrationError(
                                f"{py_file}",
                                details=f"failed to instantiate {attr_name}: {e}"
                            )
                        class_instances[attr_name] = instance
                    bound = getattr(instance, method_name)
                    mod_name, func_name = self._registration_parts(meta, py_file)
                    key = f"{namespace}.{mod_name}.{func_name}"
                    self._registry[key] = bound
                    registered_keys.add(key)

        self._module_keys[self._module_key(py_file)] = registered_keys

    def _load_module(self, namespace: str, py_file: Path):
        module = self._exec_module(namespace, py_file)
        self._register_functions(namespace, py_file, module)

    def reload_module(self, py_file_path: str):
        py_file = Path(py_file_path)
        if not self._agents_roots:
            return
        namespace = None
        for agents_root in self._agents_roots:
            namespace = agent_namespace_for_path(py_file, agents_root, "libs")
            if namespace is not None:
                break
        if namespace is None:
            return

        with self._rlock:
            old_keys = self._module_keys.pop(self._module_key(py_file), set())
            for key in old_keys:
                self._registry.pop(key, None)
            module = self._exec_module(namespace, py_file)
            self._register_functions(namespace, py_file, module)

    def lookup(self, namespace: str, module: str, name: str):
        key = f"{namespace}.{module}.{name}"
        with self._rlock:
            func = self._registry.get(key)
        if func is None:
            raise LibNotFoundError(key, details="not registered")
        return func
