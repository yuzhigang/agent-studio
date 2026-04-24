import copy


class WorldState:
    def __init__(self, instance_manager, world_id: str):
        self._im = instance_manager
        self._world_id = world_id

    def set_instance_manager(self, instance_manager) -> None:
        self._im = instance_manager

    def snapshot(self) -> dict:
        result: dict[str, list[dict]] = {}
        for inst in self._im.list_by_world(self._world_id):
            if inst.lifecycle_state == "active" and inst.world_state:
                model_name = inst.model_name
                result.setdefault(model_name, []).append(copy.deepcopy(inst.world_state))
        return result

    def get_model(self, model_name: str) -> list[dict]:
        return copy.deepcopy(self.snapshot().get(model_name, []))

    def get_instance(self, instance_id: str) -> dict | None:
        for inst in self._im.list_by_world(self._world_id):
            if inst.lifecycle_state == "active" and inst.id == instance_id:
                return copy.deepcopy(inst.world_state)
        return None

    def get_instance_state(self, instance_id: str) -> str | None:
        inst_data = self.get_instance(instance_id)
        return inst_data["state"] if inst_data else None
