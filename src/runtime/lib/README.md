# runtime.lib

Agent Studio 脚本库运行时。

## Quick Start

```python
from runtime.lib import lib_function, LibRegistry, LibProxy, SandboxExecutor

@lib_function(name="hello", namespace="shared")
def hello(args: dict) -> dict:
    return {"msg": f"Hello, {args.get('name', 'world')}!"}

registry = LibRegistry()
registry.scan("agents/")

proxy = LibProxy(default_namespace="shared")
executor = SandboxExecutor()
result = executor.execute("result = lib.hello(args)", {"args": {"name": "Alice"}, "lib": proxy})
```

## Directory Layout

- `agents/<group>/<model>/libs/` → `lib.<model>.<module>.<function>`
- `agents/shared/libs/` → `lib.shared.<module>.<function>`

Note: Use `src.runtime.lib` for imports in actual code (the package root is `src`). The example above uses `runtime.lib` as a conceptual import.
