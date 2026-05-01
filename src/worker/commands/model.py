from pathlib import Path

from src.runtime.model_loader import ModelLoader
from src.runtime.model_resolver import split_model_id
from src.worker.server.jsonrpc_ws import JsonRpcError


async def world_models_list(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    world_dir = bundle.get("world_dir")
    if world_dir is None:
        raise JsonRpcError(-32004, "world_dir not available")
    agents_dir = Path(world_dir) / "agents"
    models = []
    if agents_dir.exists():
        # Two-level iteration: namespace dirs → model dirs (skip "shared")
        for ns_dir in sorted(agents_dir.iterdir()):
            if not ns_dir.is_dir() or ns_dir.name == "shared":
                continue
            for model_dir in sorted(ns_dir.iterdir()):
                if model_dir.is_dir() and (model_dir / "model" / "index.yaml").exists():
                    model_id = f"{ns_dir.name}.{model_dir.name}"
                    try:
                        data = ModelLoader.load(str(model_dir))
                        models.append({
                            "model_id": model_id,
                            "metadata": data.get("metadata", {}),
                        })
                    except Exception:
                        pass
    return {"models": models}


async def world_models_get(manager, bundle, params):
    world_id = params.get("world_id")
    if bundle is None:
        raise JsonRpcError(-32004, f"World {world_id} not loaded")
    model_id = params.get("model_id")
    if model_id is None:
        raise JsonRpcError(-32602, "model_id required")
    world_dir = bundle.get("world_dir")
    if world_dir is None:
        raise JsonRpcError(-32004, "world_dir not available")
    try:
        namespace, model_name = split_model_id(model_id)
    except ValueError as e:
        raise JsonRpcError(-32602, str(e))
    model_path = Path(world_dir) / "agents" / namespace / model_name
    if not (model_path / "model" / "index.yaml").exists():
        raise JsonRpcError(-32004, f"Model {model_id} not found")
    data = ModelLoader.load(str(model_path))
    data["model_id"] = model_id
    return data
