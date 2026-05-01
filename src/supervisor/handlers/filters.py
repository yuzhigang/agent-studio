"""Shared instance filtering logic used by instances and scenes handlers."""


def filter_instances(instances: list[dict], *, model_id: str | None = None,
                     scope: str | None = None, lifecycle_state: str | None = None,
                     state: str | None = None, target_scope: str | None = None) -> list[dict]:
    """Filter and format raw worker instances for API response.

    Args:
        instances: Raw instance dicts from worker (with "id", "model", "scope", "state", etc.)
        model_id: Filter by model name
        scope: Filter by exact scope value
        lifecycle_state: Filter by lifecycle state
        state: Filter by state name (handles both dict {"current": "x"} and string "x")
        target_scope: Filter by scope (used by scene instance handlers)
    """
    filtered = []
    for inst in instances:
        if target_scope and inst.get("scope") != target_scope:
            continue
        if scope and inst.get("scope") != scope:
            continue
        if model_id and inst.get("model") != model_id:
            continue
        if lifecycle_state and inst.get("lifecycle_state") != lifecycle_state:
            continue
        raw_state = inst.get("state", {})
        inst_state = raw_state.get("current") if isinstance(raw_state, dict) else raw_state
        if state and inst_state != state:
            continue
        filtered.append({
            "instance_id": inst["id"],
            "model_name": inst["model"],
            "scope": inst["scope"],
            "state": inst_state,
            "lifecycle_state": inst["lifecycle_state"],
            "variables": inst.get("variables", {}),
            "attributes": inst.get("attributes", {}),
        })
    return filtered
