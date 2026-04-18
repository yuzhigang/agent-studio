"""Scan a world's agents/ directory for static instance declarations."""

from pathlib import Path

import yaml


class InstanceLoader:
    """Scan a world's agents/ directory for *.instance.yaml declarations."""

    @staticmethod
    def scan(world_dir: str) -> list[dict]:
        """Recursively scan {world_dir}/agents/**/instances/*.instance.yaml.

        Returns a list of parsed declaration dicts, each with an extra
        '_source_file' key pointing to the source path.
        """
        agents_dir = Path(world_dir) / "agents"
        if not agents_dir.exists():
            return []

        results: list[dict] = []
        for instances_dir in agents_dir.rglob("instances"):
            if not instances_dir.is_dir():
                continue
            for file_path in instances_dir.glob("*.instance.yaml"):
                if not file_path.is_file():
                    continue
                with open(file_path, "r", encoding="utf-8") as f:
                    decl = yaml.safe_load(f) or {}
                decl["_source_file"] = str(file_path)
                results.append(decl)
        return results
