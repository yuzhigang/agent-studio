import asyncio
import sys

from src.simulator.config import load_config
from src.simulator.engine import EventSimulator


def simulate_main(config_path: str) -> int:
    # Windows: force UTF-8 for stdout/stderr so Chinese characters print correctly
    if sys.platform == "win32" and "PYTEST_CURRENT_TEST" not in __import__("os").environ:
        import os
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            import io
            if hasattr(sys.stdout, "buffer") and getattr(sys.stdout, "encoding", None) != "utf-8":
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
            if hasattr(sys.stderr, "buffer") and getattr(sys.stderr, "encoding", None) != "utf-8":
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)
        except (AttributeError, OSError, ValueError):
            pass
    config = load_config(config_path)
    simulator = EventSimulator(config)
    return asyncio.run(simulator.run())
