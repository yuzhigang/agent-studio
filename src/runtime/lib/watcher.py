from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.runtime.lib.registry import LibRegistry


class _ReloadHandler(FileSystemEventHandler):
    def __init__(self, registry: LibRegistry):
        self.registry = registry

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".py"):
            self.registry.reload_module(event.src_path)


class LibWatcher:
    def __init__(self, agents_root: str, registry: LibRegistry | None = None):
        self.agents_root = agents_root
        self.registry = registry or LibRegistry(_singleton=True)
        self.observer = Observer()
        self.handler = _ReloadHandler(self.registry)

    def start(self):
        self.observer.schedule(self.handler, self.agents_root, recursive=True)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()
