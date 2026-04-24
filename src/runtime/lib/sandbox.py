import ast
import importlib
import types

from src.runtime.lib.exceptions import ScriptExecutionError, ImmutableContextError


SAFE_BUILTINS = frozenset({
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "chr", "complex", "dict", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max",
    "min", "next", "object", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "type", "vars", "zip",
    "Exception", "BaseException", "RuntimeError", "ValueError", "TypeError",
    "KeyError", "IndexError", "AttributeError", "StopIteration",
    "True", "False", "None",
})

FORBIDDEN_BUILTINS = frozenset({
    "open", "eval", "exec", "__import__", "compile",
    "getattr", "setattr", "delattr", "input", "breakpoint",
    "help", "quit", "exit",
})

PRELOADED_MODULES = {
    "math", "random", "statistics", "itertools", "functools",
    "operator", "collections", "json", "datetime", "time", "re",
    "string", "copy", "typing",
}


def _make_import_hook(allowed: set[str], extra_modules: dict | None = None):
    extra = extra_modules or {}

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        base = name.split(".")[0]
        if base in extra:
            return extra[base]
        if base not in allowed:
            raise ImportError(f"Import of '{name}' is not allowed in this sandbox")
        return __import__(name, globals, locals, fromlist, level)

    return _import


class SandboxExecutor:
    def __init__(self, registry=None):
        self.registry = registry

    @staticmethod
    def _build_shared_modules(registry):
        modules = {}
        for key, func in registry._data.items():
            parts = key.split(".")
            if len(parts) != 3 or parts[0] != "shared":
                continue
            _, mod_name, func_name = parts
            if mod_name not in modules:
                modules[mod_name] = types.ModuleType(mod_name)
            setattr(modules[mod_name], func_name, func)
        return modules

    def evaluate_expression(self, expression: str, context: dict):
        """Evaluate a single expression safely using ast.parse (eval mode)."""
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            raise ScriptExecutionError(str(e), line=e.lineno)

        safe_builtins = {
            name: __builtins__[name]
            for name in SAFE_BUILTINS
            if name in __builtins__ and name not in FORBIDDEN_BUILTINS
        }
        globals_dict = {"__builtins__": safe_builtins, **context}
        try:
            return eval(compile(tree, "<sandbox-eval>", "eval"), globals_dict)
        except Exception as e:
            raise ScriptExecutionError(str(e)) from e

    def execute(self, script: str, context: dict):
        try:
            tree = ast.parse(script, mode="exec")
        except SyntaxError as e:
            raise ScriptExecutionError(str(e), line=e.lineno)

        safe_builtins = {
            name: __builtins__[name]
            for name in SAFE_BUILTINS
            if name in __builtins__ and name not in FORBIDDEN_BUILTINS
        }

        allowed_imports = set(PRELOADED_MODULES)
        extra_modules = {}
        if self.registry is not None:
            shared_modules = self._build_shared_modules(self.registry)
            allowed_imports.update(shared_modules.keys())
            extra_modules.update(shared_modules)
        else:
            shared_modules = {}

        safe_builtins["__import__"] = _make_import_hook(allowed_imports, extra_modules)

        preloaded = {}
        for mod_name in PRELOADED_MODULES:
            try:
                preloaded[mod_name] = importlib.import_module(mod_name)
            except ImportError:
                pass

        preloaded.update(shared_modules)

        globals_dict = {"__builtins__": safe_builtins, **preloaded, **context}

        try:
            exec(compile(tree, "<sandbox>", "exec"), globals_dict)
        except Exception as e:
            if isinstance(e, ImmutableContextError):
                raise
            tb = e.__traceback__
            lineno = tb.tb_lineno if tb else None
            raise ScriptExecutionError(str(e), line=lineno) from e

        return globals_dict.get("result")
