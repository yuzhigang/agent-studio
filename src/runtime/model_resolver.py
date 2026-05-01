"""ModelResolver: resolves a modelId to a model/ directory path."""

import shutil
from pathlib import Path

from src.runtime.lib.exceptions import ModelNotFoundError


def split_model_id(model_id: str) -> tuple[str, str]:
    """Split model_id into (namespace, model_name).

    Raises ValueError if model_id contains no dot or empty parts.
    """
    if "." not in model_id:
        raise ValueError(f"modelId must contain namespace: {model_id}")
    namespace, model_name = model_id.split(".", 1)
    if not namespace:
        raise ValueError(f"namespace must not be empty: {model_id}")
    if not model_name:
        raise ValueError(f"model_name must not be empty: {model_id}")
    return namespace, model_name


class ModelResolver:
    """Resolves a modelId to a model/ directory path.

    Searches only in the world's private agents/ directory.
    Global paths are used only as templates for lazy copy via ensure().
    """

    split_model_id = staticmethod(split_model_id)

    def __init__(self, world_dir: str, global_paths: list[str]):
        """Initialize the resolver.

        Args:
            world_dir: Path to the world directory (e.g., "worlds/steel-plant-01")
            global_paths: List of paths to global model directories (e.g., ["agents/"])
        """
        self.world_dir = Path(world_dir)
        self.global_paths = [Path(p) for p in global_paths]
        self._shared_libs_copied: bool = False

    def resolve(self, model_id: str) -> Path | None:
        """Return the Path to the model/ directory, or None if not found.

        Searches world private agents only. No global fallback.
        """
        namespace, model_name = split_model_id(model_id)
        world_agents_dir = self.world_dir / "agents"
        if world_agents_dir.exists():
            return self._find_model_dir(world_agents_dir, namespace, model_name)
        return None

    def ensure(self, model_id: str) -> Path:
        """Guarantee model_id exists in world-private dir, copying from global templates if needed.

        1. Search world-local -> found -> return.
        2. Find in global templates -> copy to world -> return.
        3. Not found anywhere -> ModelNotFoundError.
        """
        namespace, model_name = split_model_id(model_id)
        world_agents_dir = self.world_dir / "agents"

        if world_agents_dir.exists():
            local = self._find_model_dir(world_agents_dir, namespace, model_name)
            if local is not None:
                return local

        for global_path in self.global_paths:
            template = self._find_model_dir(global_path, namespace, model_name)
            if template is not None:
                self._copy_from_template(template, global_path)
                self._ensure_shared_libs()
                result = self._find_model_dir(world_agents_dir, namespace, model_name)
                if result is not None:
                    return result

        raise ModelNotFoundError(model_id)

    @staticmethod
    def _find_model_dir(root: Path, namespace: str, model_name: str) -> Path | None:
        """Exact-path lookup: root/{namespace}/{model_name}/model"""
        exact = root / namespace / model_name / "model"
        return exact if exact.is_dir() else None

    def _copy_from_template(self, template_model_dir: Path, global_root: Path) -> None:
        """Copy model/ and libs/ from template agent dir to world agents/."""
        # template_model_dir is agents/{ns...}/{mid}/model/
        # template_agent_dir is agents/{ns...}/{mid}/
        template_agent_dir = template_model_dir.parent
        rel_path = template_agent_dir.relative_to(global_root)
        world_target = self.world_dir / "agents" / rel_path

        # Copy model/ directory
        world_model_dir = world_target / "model"
        self._copytree_skip_existing(template_model_dir, world_model_dir)

        # Copy libs/ directory if it exists in template
        template_libs_dir = template_agent_dir / "libs"
        if template_libs_dir.exists():
            world_libs_dir = world_target / "libs"
            self._copytree_skip_existing(template_libs_dir, world_libs_dir)

    def _ensure_shared_libs(self) -> None:
        """Copy agents/shared/libs/ to world on first ensure() call."""
        if self._shared_libs_copied:
            return
        self._shared_libs_copied = True

        for global_path in self.global_paths:
            shared_libs = global_path / "shared" / "libs"
            if shared_libs.exists():
                world_shared_libs = self.world_dir / "agents" / "shared" / "libs"
                self._copytree_skip_existing(shared_libs, world_shared_libs)
                break

    @staticmethod
    def _copytree_skip_existing(src: Path, dst: Path) -> None:
        """Recursively copy src to dst, skipping files that already exist."""
        if not src.exists():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            dst_item = dst / item.name
            if item.is_dir():
                ModelResolver._copytree_skip_existing(item, dst_item)
            else:
                if not dst_item.exists():
                    shutil.copy2(item, dst_item)
