import json
import logging
from pathlib import Path
import yaml
from src.runtime.lib.exceptions import ModelConfigError

logger = logging.getLogger(__name__)

class ModelLoader:
    @staticmethod
    def load(agent_path: str | Path) -> dict:
        agent_path = Path(agent_path)
        if not agent_path.exists():
            raise ModelConfigError(str(agent_path), "Agent path does not exist")
        if not agent_path.is_dir():
            raise ModelConfigError(str(agent_path), "Agent path must be a directory")

        model_dir = agent_path / "model"

        if model_dir.exists() and model_dir.is_dir():
            return ModelLoader._load_directory(model_dir)

        legacy_yaml = agent_path / "model.yaml"
        if legacy_yaml.exists():
            return ModelLoader._load_yaml_file(legacy_yaml)

        legacy_json = agent_path / "model.json"
        if legacy_json.exists():
            try:
                with open(legacy_json, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                raise ModelConfigError(str(legacy_json), f"JSON parse error: {e}")

        raise ModelConfigError(str(agent_path), "No model configuration found")

    @staticmethod
    def _load_yaml_file(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
                return data if data is not None else {}
            except yaml.YAMLError as e:
                raise ModelConfigError(str(path), f"YAML parse error: {e}")

    @staticmethod
    def _load_directory(model_dir: Path) -> dict:
        index_file = model_dir / "index.yaml"
        if not index_file.exists():
            raise ModelConfigError(str(model_dir), "Directory mode requires index.yaml")

        base = ModelLoader._load_yaml_file(index_file)
        known_keys = {
            "$schema", "metadata", "attributes", "variables", "derivedProperties",
            "links", "rules", "functions", "services", "states", "transitions",
            "behaviors", "events", "alarms", "schedules", "goals",
            "decisionPolicies", "memory", "plans",
        }

        for yaml_file in sorted(model_dir.glob("*.yaml"), key=lambda p: p.name.lower()):
            if yaml_file.name == "index.yaml":
                continue
            key = yaml_file.stem
            data = ModelLoader._load_yaml_file(yaml_file)
            if key in base:
                logger.warning("Key '%s' from %s overwrites existing key in index.yaml", key, yaml_file)
            if key not in known_keys:
                logger.warning("Unknown model key '%s' from file %s", key, yaml_file)
            base[key] = data

        return base
