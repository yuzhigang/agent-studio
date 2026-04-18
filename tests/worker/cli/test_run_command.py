import os
import tempfile
from src.runtime.world_registry import WorldRegistry
from src.worker.cli.run_command import _start_shared_scenes, _graceful_shutdown


def test_start_shared_scenes_restores_shared():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")
        bundle = reg.load_world("world-a")
        sm = bundle["scene_manager"]
        store = bundle["store"]
        # create a shared scene via scene manager and persist it
        sm.start("world-a", "scene-1", mode="shared")
        sm.checkpoint_scene("world-a", "scene-1")
        reg.unload_world("world-a")

        # reload and auto-start shared scenes
        bundle2 = reg.load_world("world-a")
        _start_shared_scenes(bundle2)
        assert bundle2["scene_manager"].get("world-a", "scene-1") is not None
        reg.unload_world("world-a")


def test_graceful_shutdown_unloads_and_releases_lock():
    with tempfile.TemporaryDirectory() as tmp:
        reg = WorldRegistry(base_dir=tmp)
        reg.create_world("world-a")
        bundle = reg.load_world("world-a")
        _graceful_shutdown(bundle)
        assert reg.get_loaded_world("world-a") is None
        # lock should be released, so reload works
        bundle2 = reg.load_world("world-a")
        assert bundle2 is not None
        reg.unload_world("world-a")
