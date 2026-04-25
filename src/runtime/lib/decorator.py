def lib_function(*, name: str | None = None, module: str | None = None):
    def decorator(func):
        func._lib_meta = {
            "name": name,
            "module": module,
            "entrypoint": func.__name__,
            "func": func,
        }
        return func
    return decorator
