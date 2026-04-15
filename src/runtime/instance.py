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
        return Instance(
            instance_id=self.instance_id,
            model_name=self.model_name,
            project_id=self.project_id,
            scope=self.scope,
            attributes=copy.deepcopy(self.attributes),
            variables=copy.deepcopy(self.variables),
            links=copy.deepcopy(self.links),
            memory=copy.deepcopy(self.memory),
            state=copy.deepcopy(self.state),
            audit=copy.deepcopy(self.audit),
            model=copy.deepcopy(self.model),
        )
