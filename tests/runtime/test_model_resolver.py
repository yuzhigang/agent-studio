"""Tests for ModelResolver."""

import pytest
from pathlib import Path

from src.runtime.model_resolver import ModelResolver
from src.runtime.lib.exceptions import ModelNotFoundError


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
        """World-private models are found; global models are ignored by resolve()."""
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

    def test_resolve_does_not_fallback_to_global(self, tmp_path: Path) -> None:
        """resolve() no longer falls back to global paths."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "model.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.resolve("ladle")

        assert result is None

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        """Test returning None when model is not found in world."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("nonexistent")

        assert result is None

    def test_resolve_no_world_agents_dir(self, tmp_path: Path) -> None:
        """Test that resolver handles missing world agents/ directory gracefully."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is None

    def test_resolve_model_in_flat_namespace(self, tmp_path: Path) -> None:
        """Test finding a model under a namespace subdirectory."""
        world_dir = tmp_path / "world"
        agents_dir = world_dir / "agents"
        model_dir = agents_dir / "namespace" / "ladle" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [])
        result = resolver.resolve("ladle")

        assert result is not None
        assert result.resolve() == model_dir.resolve()

    def test_ensure_copies_from_global(self, tmp_path: Path) -> None:
        """ensure() copies global template to world when missing locally."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("ladle")

        assert result is not None
        assert result.resolve() == (world_dir / "agents" / "ladle" / "model").resolve()
        assert (world_dir / "agents" / "ladle" / "model" / "index.yaml").exists()

    def test_ensure_skips_existing_world_model(self, tmp_path: Path) -> None:
        """ensure() does not copy when world already has the model."""
        world_dir = tmp_path / "world"
        world_model_dir = world_dir / "agents" / "ladle" / "model"
        world_model_dir.mkdir(parents=True)
        (world_model_dir / "index.yaml").write_text("name: world-ladle")

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: global-ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("ladle")

        assert result.resolve() == world_model_dir.resolve()
        content = (world_model_dir / "index.yaml").read_text()
        assert "world-ladle" in content

    def test_ensure_raises_when_not_found_anywhere(self, tmp_path: Path) -> None:
        """ensure() raises ModelNotFoundError when model is missing everywhere."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()
        global_dir = tmp_path / "global"
        global_dir.mkdir()

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        with pytest.raises(ModelNotFoundError):
            resolver.ensure("nonexistent")

    def test_ensure_copies_shared_libs(self, tmp_path: Path) -> None:
        """ensure() copies shared/libs/ from global on first call."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")
        shared_libs = global_dir / "shared" / "libs"
        shared_libs.mkdir(parents=True)
        (shared_libs / "util.py").write_text("def hello(): pass")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        resolver.ensure("ladle")

        assert (world_dir / "agents" / "shared" / "libs" / "util.py").exists()

    def test_ensure_preserves_namespace_structure(self, tmp_path: Path) -> None:
        """ensure() preserves namespace path when copying from global."""
        world_dir = tmp_path / "world"
        world_dir.mkdir()

        global_dir = tmp_path / "global"
        global_model_dir = global_dir / "logistics" / "ladle" / "model"
        global_model_dir.mkdir(parents=True)
        (global_model_dir / "index.yaml").write_text("name: ladle")

        resolver = ModelResolver(str(world_dir), [str(global_dir)])
        result = resolver.ensure("ladle")

        expected = world_dir / "agents" / "logistics" / "ladle" / "model"
        assert result.resolve() == expected.resolve()
