"""ModelResolver: resolves a modelId to a model/ directory path."""

from pathlib import Path


class ModelResolver:
    """Resolves a modelId to a model/ directory path.

    Searches in priority order:
    1. World's private agents/ directory: {world_dir}/agents/**/{model_id}/model/
    2. Global model paths: each global path, looking for **/{model_id}/model/
    """

    def __init__(self, world_dir: str, global_paths: list[str]):
        """Initialize the resolver.

        Args:
            world_dir: Path to the world directory (e.g., "worlds/steel-plant-01")
            global_paths: List of paths to global model directories (e.g., ["agents/"])
        """
        self.world_dir = Path(world_dir)
        self.global_paths = [Path(p) for p in global_paths]

    def resolve(self, model_id: str) -> Path | None:
        """Return the Path to the model/ directory, or None if not found.

        Searches world private agents first, then falls back to global paths.
        """
        # Search world private agents first
        world_agents_dir = self.world_dir / "agents"
        if world_agents_dir.exists():
            result = self._find_model_dir(world_agents_dir, model_id)
            if result is not None:
                return result

        # Fall back to global paths in order
        for global_path in self.global_paths:
            if global_path.exists():
                result = self._find_model_dir(global_path, model_id)
                if result is not None:
                    return result

        return None

    @staticmethod
    def _find_model_dir(root: Path, model_id: str) -> Path | None:
        """Recursively search root for */{model_id}/model directory.

        Args:
            root: Directory to search under
            model_id: The model identifier to find

        Returns:
            Path to the model/ directory if found, None otherwise.
        """
        pattern = f"{model_id}/model"
        for match in root.rglob(pattern):
            if match.is_dir():
                return match
        return None
