from src.runtime.lib.registry import LibRegistry
from src.runtime.lib.exceptions import LibNotFoundError


class _LibProxyNode:
    def __init__(self, registry: LibRegistry, path: list[str], default_namespace: str | None, lib_context: dict | None):
        self._registry = registry
        self._path = path
        self._default_namespace = default_namespace
        self._lib_context = lib_context

    def __getattr__(self, name: str):
        return _LibProxyNode(self._registry, self._path + [name], self._default_namespace, self._lib_context)

    def __call__(self, *args, **kwargs):
        if len(self._path) < 2:
            raise LibNotFoundError(".".join(self._path), details="incomplete path")

        if len(self._path) == 2:
            # lib.module.name → default_namespace.module.name
            if self._path[0] == "shared":
                raise LibNotFoundError(".".join(self._path), details="shared lib calls require module.function")
            if not self._default_namespace:
                raise LibNotFoundError(".".join(self._path), details="no default namespace")
            candidates = [f"{self._default_namespace}.{self._path[0]}.{self._path[1]}"]
        elif len(self._path) == 3 and self._path[0] == "shared":
            # lib.shared.module.name
            candidates = [".".join(self._path)]
        else:
            raise LibNotFoundError(".".join(self._path), details="cross-agent lib calls are not allowed")

        func = None
        for key in candidates:
            func = self._registry._data.get(key)
            if func is not None:
                break

        if func is None:
            raise LibNotFoundError(".".join(self._path), details="not registered")

        # Inject LibContext into bound method's instance
        instance = getattr(func, '__self__', None)
        if instance and self._lib_context is not None:
            instance._context = self._lib_context

        return func(*args, **kwargs)


class LibProxy:
    def __init__(self, default_namespace: str | None = None, registry: LibRegistry | None = None, lib_context: dict | None = None):
        self._registry = registry or LibRegistry(_singleton=True)
        self._default_namespace = default_namespace
        self._lib_context = lib_context

    def __getattr__(self, name: str):
        return _LibProxyNode(self._registry, [name], self._default_namespace, self._lib_context)
