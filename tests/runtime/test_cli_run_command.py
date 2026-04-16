import os
import tempfile
from src.runtime.project_registry import ProjectRegistry
from src.runtime.cli.run_command import _start_shared_scenes, _graceful_shutdown


def test_start_shared_scenes_restores_shared():
    with tempfile.TemporaryDirectory() as tmp:
        reg = ProjectRegistry(base_dir=tmp)
        reg.create_project("proj-a")
        bundle = reg.load_project("proj-a")
        sm = bundle["scene_manager"]
        store = bundle["store"]
        # create a shared scene via scene manager and persist it
        sm.start("proj-a", "scene-1", mode="shared")
        sm.checkpoint_scene("proj-a", "scene-1")
        reg.unload_project("proj-a")

        # reload and auto-start shared scenes
        bundle2 = reg.load_project("proj-a")
        _start_shared_scenes(bundle2)
        assert bundle2["scene_manager"].get("proj-a", "scene-1") is not None
        reg.unload_project("proj-a")


def test_graceful_shutdown_unloads_and_releases_lock():
    with tempfile.TemporaryDirectory() as tmp:
        reg = ProjectRegistry(base_dir=tmp)
        reg.create_project("proj-a")
        bundle = reg.load_project("proj-a")
        _graceful_shutdown(bundle)
        assert reg.get_loaded_project("proj-a") is None
        # lock should be released, so reload works
        bundle2 = reg.load_project("proj-a")
        assert bundle2 is not None
        reg.unload_project("proj-a")
