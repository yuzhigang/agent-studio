from pathlib import Path


def agent_namespace_for_path(path: Path, agents_root: Path, anchor: str) -> str | None:
    try:
        rel = path.relative_to(agents_root)
    except ValueError:
        return None

    parts = rel.parts
    try:
        anchor_index = parts.index(anchor)
    except ValueError:
        return None

    agent_parts = parts[:anchor_index]
    if not agent_parts:
        return None
    if len(agent_parts) == 1 and agent_parts[0] == "shared":
        return "shared"
    return ".".join(agent_parts)
