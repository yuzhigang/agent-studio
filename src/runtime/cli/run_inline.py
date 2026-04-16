import os
import signal
import sys

from src.runtime.project_registry import ProjectRegistry


def run_inline(project_dirs):
    registries = _load_projects(project_dirs)

    def _shutdown(signum, frame):
        print("Shutting down inline runtime...")
        for registry in registries:
            for project_id in list(registry._loaded.keys()):
                registry.unload_project(project_id)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import threading
    threading.Event().wait()
    return 0


def _load_projects(project_dirs):
    registries = []
    for project_dir in project_dirs:
        base_dir = os.path.dirname(os.path.abspath(project_dir))
        project_id = os.path.basename(os.path.abspath(project_dir))
        registry = ProjectRegistry(base_dir=base_dir)
        registry.load_project(project_id)
        registries.append(registry)
    return registries
