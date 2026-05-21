from dataclasses import dataclass, field
import copy


@dataclass
class Instance:
    instance_id: str
    model_name: str
    world_id: str
    scope: str
    _agent_namespace: str | None = field(default=None, repr=False)
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
    _audit_fields: dict = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        return self.instance_id

    @property
    def world_state(self) -> dict:
        result = {
            "id": self.instance_id,
            "model_name": self.model_name,
            "state": self.state.get("current"),
            "updated_at": self.state.get("enteredAt"),
            "lifecycle_state": self.lifecycle_state,
        }
        model = self.model or {}
        for name, defn in (model.get("variables") or {}).items():
            if defn.get("shared"):
                result[name] = copy.deepcopy(self.variables.get(name))
        for name, defn in (model.get("attributes") or {}).items():
            if defn.get("shared"):
                result[name] = copy.deepcopy(self.attributes.get(name))
        return result

    def deep_copy(self) -> "Instance":
        clone = copy.deepcopy(self)
        clone._audit_fields = {}
        return clone

    def _ensure_audit_fields(self) -> None:
        if self._audit_fields or not self.model:
            return
        for name, defn in (self.model.get("variables") or {}).items():
            if defn.get("audit"):
                self._audit_fields[name] = "variables"
        for name, defn in (self.model.get("attributes") or {}).items():
            if defn.get("audit"):
                self._audit_fields[name] = "attributes"
        for name, defn in (self.model.get("derivedProperties") or {}).items():
            if defn.get("audit"):
                self._audit_fields[name] = "derived"

    def _is_audit_field(self, field_path: str) -> bool:
        self._ensure_audit_fields()
        parts = field_path.split(".")
        if len(parts) != 2:
            return False
        section, name = parts
        return self._audit_fields.get(name) == section
