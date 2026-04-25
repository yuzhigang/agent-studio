from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MessageEnvelope:
    message_id: str
    world_id: str
    event_type: str
    payload: dict[str, Any]
    source: str | None = None
    scope: str = "world"
    target: str | None = None
    trace_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
