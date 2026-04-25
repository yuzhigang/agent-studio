from src.runtime.messaging.envelope import MessageEnvelope
from src.runtime.messaging.world_receiver import WorldMessageReceiver


class WorldMessageIngress(WorldMessageReceiver):
    def __init__(self, event_emitter):
        self._event_emitter = event_emitter

    async def receive(self, envelope: MessageEnvelope) -> None:
        self._event_emitter.publish_internal(
            event_type=envelope.event_type,
            payload=envelope.payload,
            source=envelope.source or "external",
            scope=envelope.scope,
            target=envelope.target,
        )
