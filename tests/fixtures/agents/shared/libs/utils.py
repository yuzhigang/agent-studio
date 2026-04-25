from src.runtime.lib.decorator import lib_function


@lib_function()
def uppercase(args: dict) -> dict:
    text = args.get("text", "")
    return {"text": text.upper()}
