from dataclasses import dataclass, field
import copy


@dataclass
class Instance:
    instance_id: str
    model_name: str
    world_id: str
    scope: str
    model_version: str | None = field(default=None)
    attributes: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    bindings: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    state: dict = field(default_factory=lambda: {"current": None, "enteredAt": None})
    audit: dict = field(default_factory=lambda: {"version": 0, "updatedAt": None, "lastEventId": None})
    lifecycle_state: str = field(default="active")
    model: dict | None = field(default=None, repr=False)
    snapshot: dict = field(default_factory=dict, repr=False)
    _audit_fields: dict = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        return self.instance_id

    @property
    def world_state(self) -> dict:
        return {
            "id": self.instance_id,
            "state": self.state.get("current"),
            "updated_at": self.state.get("enteredAt"),
            "lifecycle_state": self.lifecycle_state,
            "snapshot": copy.deepcopy(self.snapshot),
        }

    def deep_copy(self) -> "Instance":
        clone = copy.deepcopy(self)
        clone.snapshot = {}
        clone._audit_fields = {}
        return clone

    def _update_snapshot(self) -> dict:
        if not self._audit_fields and self.model:
            for name, defn in (self.model.get("variables") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "variables"
            for name, defn in (self.model.get("attributes") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "attributes"
            for name, defn in (self.model.get("derivedProperties") or {}).items():
                if defn.get("audit"):
                    self._audit_fields[name] = "derived"

        if self._audit_fields:
            self.snapshot = {}
            for field_name, source in self._audit_fields.items():
                if source == "variables":
                    self.snapshot[field_name] = copy.deepcopy(self.variables.get(field_name))
                elif source == "attributes":
                    self.snapshot[field_name] = copy.deepcopy(self.attributes.get(field_name))
                elif source == "derived":
                    self.snapshot[field_name] = copy.deepcopy(
                        self.variables.get(field_name, self.attributes.get(field_name))
                    )
        return self.snapshot
