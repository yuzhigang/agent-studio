"""Tests for ModelResolver."""

import pytest
from pathlib import Path

from src.runtime.model_resolver import ModelResolver


class TestModelResolver:
    """Test suite for ModelResolver."""

    def test_resolve_in_world_agents(self, tmp_path: Path) -> None:
        """Test finding a model in the world's agents directory."""
        world_dir = tmp_path / "world"
        agents_dir = world_dir / "agents"
        model_dir = agents_dir / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_resolve_prefers_world_over_global(self, tmp_path: Path) -> None:
        """Test that world private models take precedence over global models."""
        world_dir = tmp_path / "world"
        world_agents_dir = world_dir / "agents"
        world_model_dir = world_agents_dir / "ladle" / "model"
        world_model_dir.mkdir(parents=True)
        (world_model_dir / "model.yaml").write_text("name: world-ladle")

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == world_model_dir.resolve()

    def test_resolve_falls_back_to_global(self, tmp_path: Path) -> None:
        """Test falling back to global paths when model not in world."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == global_model_dir.resolve()

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        """Test returning None when model is not found anywhere."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("nonexistent")

        assert result is None

    def test_resolve_no_world_agents_dir(self, tmp_path: Path) -> None:
        """Test that resolver handles missing world agents/ directory gracefully."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()
        # Note: no agents/ directory created

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == global_model_dir.resolve()

    def test_resolve_model_in_flat_namespace(self, tmp_path: Path) -> None:
        """Test finding a model under a namespace subdirectory."""
        world_dir = tmp_path / "world"
        agents_dir = world_dir / "agents"
        # Model is under a namespace subdirectory
        model_dir = agents_dir / "namespace" / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_resolve_multiple_global_paths_checks_in_order(self, tmp_path: Path) -> None:
        """Test that multiple global paths are checked in order."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir1 = tmp_path / "global1"
        global_dir1.mkdir()

        global_dir2 = tmp_path / "global2"
        global_model_dir = global_dir2 / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global2-ladle")

        global_dir3 = tmp_path / "global3"
        global3_model_dir = global_dir3 / "ladle" / "model"
        global3_model_dir.mkdir(parents=True)
        (global3_model_dir / "model.yaml").write_text("name: global3-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir1), str(global_dir2), str(global_dir3)])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == global_model_dir.resolve()
