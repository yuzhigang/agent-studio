from dataclasses import dataclass, field
import copy


@dataclass
class Instance:
    instance_id: str
    model_name: str
    project_id: str
    scope: str
    attributes: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    state: dict = field(default_factory=lambda: {"current": None, "enteredAt": None})
    audit: dict = field(default_factory=lambda: {"version": 0, "updatedAt": None, "lastEventId": None})
    model: dict | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.instance_id

    def deep_copy(self) -> "Instance":
        return copy.deepcopy(self)
