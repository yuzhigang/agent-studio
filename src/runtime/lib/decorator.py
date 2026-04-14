def lib_function(*, name: str, namespace: str, readonly: bool = False):
    def decorator(func):
        func._lib_meta = {
            "name": name,
            "namespace": namespace,
            "readonly": readonly,
            "entrypoint": func.__name__,
            "func": func,
        }
        return func
    return decorator
