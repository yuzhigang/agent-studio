from src.runtime.lib.decorator import lib_function


@lib_function(name="uppercase", namespace="shared", readonly=True)
def uppercase(args: dict) -> dict:
    text = args.get("text", "")
    return {"text": text.upper()}
