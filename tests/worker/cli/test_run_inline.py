import os
import tempfile
from src.runtime.project_registry import ProjectRegistry
from src.worker.cli.run_inline import _load_projects


def test_load_projects_inline():
    with tempfile.TemporaryDirectory() as tmp:
        reg1 = ProjectRegistry(base_dir=tmp)
        reg1.create_project("factory-01")
        reg2 = ProjectRegistry(base_dir=tmp)
        reg2.create_project("factory-02")
        dirs = [os.path.join(tmp, "factory-01"), os.path.join(tmp, "factory-02")]
        registries = _load_projects(dirs)
        assert registries[0].get_loaded_project("factory-01") is not None
        assert registries[1].get_loaded_project("factory-02") is not None
        for r in registries:
            for pid in list(r._loaded.keys()):
                r.unload_project(pid)
