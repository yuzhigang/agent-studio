"""Tests for ModelResolver with mandatory namespace."""

import pytest
from pathlib import Path

from src.runtime.model_resolver import ModelResolver
from src.runtime.lib.exceptions import ModelNotFoundError


class TestSplitModelId:
    """Test split_model_id parser."""

    def test_simple(self):
        assert ModelResolver.split_model_id("core.ladle") == ("core", "ladle")

    def test_model_name_with_dot(self):
        assert ModelResolver.split_model_id("logistics.sensor.v2") == ("logistics", "sensor.v2")

    def test_no_dot_raises(self):
        with pytest.raises(ValueError, match="must contain namespace"):
            ModelResolver.split_model_id("ladle")

    def test_empty_namespace_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            ModelResolver.split_model_id(".ladle")

    def test_empty_model_name_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            ModelResolver.split_model_id("core.")

    def test_deep_namespace_model_name(self):
        """a.b.ladle -> namespace='a', model_name='b.ladle' (valid)"""
        assert ModelResolver.split_model_id("a.b.ladle") == ("a", "b.ladle")


class TestModelResolver:
    """Test suite for ModelResolver with namespace-aware paths."""

    def test_resolve_in_world_agents(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        model_dir = world_dir / "agents" / "core" / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("core.ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_resolve_no_world_agents_dir(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("core.ladle")

        assert result is None

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("core.nonexistent")

        assert result is None

    def test_resolve_invalid_model_id_raises(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        with pytest.raises(ValueError, match="must contain namespace"):
            resolver.resolve("ladle")

    def test_ensure_copies_from_global(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "core" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("core.ladle")

        assert result.resolve() == (world_dir / "agents" / "core" / "ladle" / "model").resolve()
        assert (world_dir / "agents" / "core" / "ladle" / "model" / "index.yaml").exists()

    def test_ensure_skips_existing_world_model(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_model_dir = world_dir / "agents" / "core" / "ladle" / "model"
        world_model_dir.mkdir(parents=True)
        (world_model_dir / "index.yaml").write_text("name: world-ladle")

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "core" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("core.ladle")

        assert result.resolve() == world_model_dir.resolve()
        assert "world-ladle" in (world_model_dir / "index.yaml").read_text()

    def test_ensure_raises_when_not_found_anywhere(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()
        global_dir = tmp_path / "global"
        global_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        with pytest.raises(ModelNotFoundError):
            resolver.ensure("core.nonexistent")

    def test_ensure_copies_shared_libs(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "core" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")
        shared_libs = global_dir / "shared" / "libs"
        shared_libs.mkdir(parents=True)
        (shared_libs / "util.py").write_text("def hello(): pass")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        resolver.ensure("core.ladle")

        assert (world_dir / "agents" / "shared" / "libs" / "util.py").exists()

    def test_ensure_preserves_namespace_structure(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "logistics" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("logistics.ladle")

        expected = world_dir / "agents" / "logistics" / "ladle" / "model"
        assert result.resolve() == expected.resolve()

    def test_same_name_different_namespace(self, tmp_path: Path) -> None:
        world_dir = tmp_path / "world"
        agents = world_dir / "agents"

        (agents / "logistics" / "ladle" / "model").mkdir(parents=True)
        (agents / "steel" / "ladle" / "model").mkdir(parents=True)

        resolver = ModelResolver(str(world_dir), [])
        assert resolver.resolve("logistics.ladle") == agents / "logistics" / "ladle" / "model"
        assert resolver.resolve("steel.ladle") == agents / "steel" / "ladle" / "model"
