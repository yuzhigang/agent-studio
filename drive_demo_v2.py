#!/usr/bin/env python3
"""Verify static instance declarations are auto-loaded when world loads."""
import asyncio
from src.runtime.world_registry import WorldRegistry

async def main():
    # Clean start: remove old runtime.db
    import os
    for f in ["worlds/demo-world/runtime.db", "worlds/demo-world/.lock", "worlds/demo-world/.lockfile"]:
        if os.path.exists(f):
            os.remove(f)

    registry = WorldRegistry()
    bundle = registry.load_world("demo-world")

    im = bundle["instance_manager"]
    bus_reg = bundle["event_bus_registry"]
    event_bus = bus_reg.get_or_create("demo-world")

    # Verify instance was auto-loaded
    inst = im.get("demo-world", "sensor-01")
    assert inst is not None, "Instance sensor-01 should be auto-loaded!"
    print(f"✅ Auto-loaded: {inst.instance_id}")
    print(f"   model_name: {inst.model_name}")
    print(f"   state: {inst.state}")
    print(f"   variables: {inst.variables}")
    print(f"   attributes: {inst.attributes}")

    # Verify behavior works by sending beat events
    print("\n--- Sending 3 beat events ---")
    for i in range(3):
        event_bus.publish("beat", {"seq": i}, source="driver", scope="world")
        await asyncio.sleep(0.3)

    inst = im.get("demo-world", "sensor-01")
    count = inst.variables.get("count", 0)
    print(f"\n✅ Final count: {count}")
    assert count == 3, f"Expected count=3, got {count}"

    registry.unload_world("demo-world")
    print("\n✅ All checks passed!")

if __name__ == "__main__":
    asyncio.run(main())
