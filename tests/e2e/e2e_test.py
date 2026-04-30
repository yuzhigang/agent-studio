#!/usr/bin/env python3
"""端到端测试：加载世界，验证状态机事件驱动迁移与触发器级联。"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.runtime.world_registry import WorldRegistry


def main():
    print("=" * 60)
    print("端到端测试：Trigger 框架 + 状态机迁移")
    print("=" * 60)

    registry = WorldRegistry(
        base_dir="worlds",
        global_model_paths=["agents"],
    )

    print("\n[1] 加载世界 demo-world ...")
    bundle = registry.load_world("demo-world")
    print(f"    ✓ 世界加载成功: {bundle['world_id']}")

    im = bundle["instance_manager"]
    bus = bundle["event_bus_registry"].get_or_create("demo-world")

    print("\n[2] 检查静态实例声明加载 ...")
    inst = im.get("demo-world", "sensor-01", scope="world")
    if inst is None:
        print("    ✗ sensor-01 未找到!")
        registry.unload_world("demo-world")
        return 1

    print(f"    ✓ 实例找到: {inst.id}")
    print(f"      model_name: {inst.model_name}")
    print(f"      state: {inst.state}")
    print(f"      attributes: {inst.attributes}")
    print(f"      variables: {inst.variables}")

    assert inst.model_name == "logistics.heartbeat"
    assert inst.state.get("current") == "idle"
    assert inst.attributes.get("interval") == 500
    assert inst.attributes.get("threshold") == 80.0
    assert inst.variables.get("count") == 0
    assert inst.variables.get("temperature") == 30
    assert inst.variables.get("alertCount") == 0
    print("    ✓ 所有声明值验证通过")

    # --- 测试 1: idle -(start)-> monitoring ---
    print("\n[3] 发送 'start' 事件 → 状态迁移 idle → monitoring ...")
    bus.publish("start", {}, source="test", scope="world")
    time.sleep(0.1)
    print(f"      state: {inst.state.get('current')}")
    assert inst.state.get("current") == "monitoring"
    print("    ✓ 状态迁移成功 idle → monitoring")

    # --- 测试 2: tick 事件更新温度 → condition 自动触发 alert ---
    print("\n[4] 发送 'tick' 事件 (temperature=85) → 温度更新 + ConditionTrigger 自动迁移 ...")
    bus.publish("tick", {"temperature": 85.0}, source="test", scope="world")
    time.sleep(0.1)
    print(f"      temperature: {inst.variables.get('temperature')}")
    print(f"      maxRecorded: {inst.variables.get('maxRecorded')}")
    print(f"      state: {inst.state.get('current')}")
    print(f"      alertCount: {inst.variables.get('alertCount')}")
    assert inst.variables.get("temperature") == 85.0
    assert inst.variables.get("maxRecorded") == 85.0
    assert inst.state.get("current") == "alert", \
        f"状态应为 alert (condition trigger 自动迁移), 得到 {inst.state.get('current')}"
    print("    ✓ ConditionTrigger 自动迁移: monitoring → alert")

    # --- 测试 3: reset 事件 → idle ---
    print("\n[5] 发送 'reset' 事件 → 状态迁移 alert → idle ...")
    bus.publish("reset", {}, source="test", scope="world")
    time.sleep(0.1)
    print(f"      state: {inst.state.get('current')}")
    assert inst.state.get("current") == "idle"
    print("    ✓ 状态迁移成功 alert → idle")

    # --- 测试 4: 重新 start → monitoring，然后 stop → idle ---
    print("\n[6] 再次 start → monitoring，然后 stop → idle ...")
    bus.publish("start", {}, source="test", scope="world")
    time.sleep(0.1)
    assert inst.state.get("current") == "monitoring"
    bus.publish("stop", {}, source="test", scope="world")
    time.sleep(0.1)
    assert inst.state.get("current") == "idle"
    print("    ✓ 完整状态循环: idle → monitoring → idle")

    # --- 测试 5: beat 事件 ---
    print("\n[7] 发送 'beat' 事件 → 触发心跳行为 ...")
    bus.publish("beat", {}, source="test", scope="world")
    time.sleep(0.1)
    print(f"      count: {inst.variables.get('count')}")
    print(f"      lastBeat: {inst.variables.get('lastBeat')}")
    assert inst.variables.get("count") == 1
    assert inst.variables.get("lastBeat") != ""
    print("    ✓ 心跳行为触发成功")

    # --- 测试 6: dispatchAssigned 事件 ---
    print("\n[8] 发送 'dispatchAssigned' 事件 → 触发派工行为 ...")
    bus.publish("dispatchAssigned", {"task": "inspect-furnace"}, source="test", scope="world")
    time.sleep(0.1)
    print("    ✓ 派工行为触发成功")

    # 卸载
    print("\n[9] 卸载世界 ...")
    registry.unload_world("demo-world")
    print("    ✓ 世界卸载成功")

    print("\n" + "=" * 60)
    print("✅ 端到端测试通过!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
