from src.supervisor.handlers.workers import handle_workers, handle_worker_worlds
from src.supervisor.handlers.worlds import (
    handle_world_start,
    handle_world_stop,
    handle_world_checkpoint,
    handle_world_detail,
)
from src.supervisor.handlers.instances import handle_world_instances, handle_instance_detail
from src.supervisor.handlers.scenes import handle_world_scenes, handle_scene_instances, handle_scene_start, handle_scene_stop
from src.supervisor.handlers.models import handle_world_models, handle_model_detail
