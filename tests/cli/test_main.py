from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from src.cli.main import main, sync_models


def test_list_instances_no_args():
    with pytest.raises(SystemExit):
        main(["list-instances"])


def test_sync_models_namespaced_discovery(tmp_path: Path) -> None:
    """sync-models discovers namespaced models and copies them to world."""
    agents = tmp_path / "agents"
    (agents / "core" / "ladle" / "model").mkdir(parents=True)
    (agents / "core" / "ladle" / "model" / "index.yaml").write_text("name: ladle")
    (agents / "logistics" / "sensor" / "model").mkdir(parents=True)
    (agents / "logistics" / "sensor" / "model" / "index.yaml").write_text("name: sensor")

    world_dir = tmp_path / "world"
    world_dir.mkdir()

    result = sync_models(str(world_dir), global_paths=[str(agents)])
    assert result == 0
    assert (world_dir / "agents" / "core" / "ladle" / "model" / "index.yaml").exists()
    assert (world_dir / "agents" / "logistics" / "sensor" / "model" / "index.yaml").exists()


def test_sync_models_skips_existing(tmp_path: Path) -> None:
    """sync-models skips existing world models."""
    agents = tmp_path / "agents"
    (agents / "core" / "ladle" / "model").mkdir(parents=True)
    (agents / "core" / "ladle" / "model" / "index.yaml").write_text("global: 1")

    world_dir = tmp_path / "world"
    world_model = world_dir / "agents" / "core" / "ladle" / "model"
    world_model.mkdir(parents=True)
    (world_model / "index.yaml").write_text("world: 1")

    with patch("src.cli.main.input", return_value="n"):
        result = sync_models(str(world_dir), global_paths=[str(agents)])
    assert result == 0
    # Should not overwrite existing file
    assert "world: 1" in (world_model / "index.yaml").read_text()
