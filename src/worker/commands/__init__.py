from src.worker.commands.world import (
    world_checkpoint,
    world_get_status,
    world_reload,
    world_remove,
    world_start,
    world_stop,
)
from src.worker.commands.instance import world_instances_get, world_instances_list
from src.worker.commands.scene import scene_start, scene_stop, world_scenes_list
from src.worker.commands.model import world_models_get, world_models_list
from src.worker.commands.message_hub import message_hub_publish, message_hub_publish_batch

_REGISTRY = {
    "world.stop": world_stop,
    "world.remove": world_remove,
    "world.checkpoint": world_checkpoint,
    "world.getStatus": world_get_status,
    "world.instances.list": world_instances_list,
    "world.instances.get": world_instances_get,
    "world.start": world_start,
    "world.reload": world_reload,
    "scene.start": scene_start,
    "scene.stop": scene_stop,
    "world.scenes.list": world_scenes_list,
    "world.models.list": world_models_list,
    "world.models.get": world_models_get,
    "messageHub.publish": message_hub_publish,
    "messageHub.publishBatch": message_hub_publish_batch,
}


def get_handler(method: str):
    return _REGISTRY.get(method)
