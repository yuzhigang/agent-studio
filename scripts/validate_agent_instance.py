#!/usr/bin/env python3

import json
import sys
from pathlib import Path


DEFINITION_KEYS = {
    "type",
    "title",
    "description",
    "default",
    "minimum",
    "maximum",
    "nullable",
    "x-unit",
    "x-rules",
    "unit",
    "isCustom"
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def add_error(errors, message):
    errors.append(message)


def validate_top_level(instance, errors):
    if instance.get("$schema") != "https://agent-studio.io/schema/v2/instance":
        add_error(errors, "Top-level $schema must be https://agent-studio.io/schema/v2/instance")
    if not instance.get("id"):
        add_error(errors, "id is required")
    if not instance.get("modelId"):
        add_error(errors, "modelId is required")
    if not instance.get("state"):
        add_error(errors, "state is required")


def validate_runtime_values(instance, errors):
    for section_name in ("attributes", "variables"):
        section = instance.get(section_name, {})
        if not isinstance(section, dict):
            add_error(errors, f"{section_name} must be an object")
            continue

        for key, value in section.items():
            if isinstance(value, dict):
                if "bind" in value:
                    add_error(errors, f"{section_name}.{key} still contains nested bind; move it to top-level bindings")
                if DEFINITION_KEYS.intersection(value.keys()):
                    add_error(errors, f"{section_name}.{key} looks like a field definition, not a runtime value")


def validate_bindings(instance, errors):
    bindings = instance.get("bindings", {})
    variables = instance.get("variables", {})

    if not isinstance(bindings, dict):
        add_error(errors, "bindings must be an object when present")
        return

    for key, binding in bindings.items():
        if key not in variables:
            add_error(errors, f"bindings.{key} does not map to an existing variable")
        if not isinstance(binding, dict):
            add_error(errors, f"bindings.{key} must be an object")
            continue
        if "source" not in binding:
            add_error(errors, f"bindings.{key}.source is required")


def validate_cortex_runtime(instance, errors):
    for goal in instance.get("activeGoals", []):
        if "goalId" not in goal:
            add_error(errors, "activeGoals item is missing goalId")
        if "status" not in goal:
            add_error(errors, "activeGoals item is missing status")

    current_plan = instance.get("currentPlan")
    if current_plan:
        for required_key in ("id", "planType", "status"):
            if required_key not in current_plan:
                add_error(errors, f"currentPlan.{required_key} is required")
        for index, step in enumerate(current_plan.get("steps", [])):
            if "service" not in step:
                add_error(errors, f"currentPlan.steps[{index}].service is required")


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_agent_instance.py <instance.json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    instance = load_json(path)
    errors = []

    validate_top_level(instance, errors)
    validate_runtime_values(instance, errors)
    validate_bindings(instance, errors)
    validate_cortex_runtime(instance, errors)

    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        sys.exit(1)

    print(f"{path.name} validation passed")


if __name__ == "__main__":
    main()
