import copy


class WorldState:
    def __init__(self, instance_manager, world_id: str):
        self._im = instance_manager
        self._world_id = world_id

    def snapshot(self) -> dict:
        result: dict[str, list[dict]] = {}
        for inst in self._im.list_by_world(self._world_id):
            if inst.lifecycle_state == "active" and inst.world_state:
                model_name = inst.model_name
                result.setdefault(model_name, []).append(copy.deepcopy(inst.world_state))
        return result
