def lib_function(*, name: str | None = None, namespace: str | None = None):
    def decorator(func):
        func._lib_meta = {
            "name": name,
            "namespace": namespace,
            "entrypoint": func.__name__,
            "func": func,
        }
        return func
    return decorator
