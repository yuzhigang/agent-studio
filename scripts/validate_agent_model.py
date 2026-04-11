#!/usr/bin/env python3

import json
import re
import sys
from pathlib import Path


REFERENCE_RE = re.compile(r"this\.(attributes|variables|derivedProperties)\.([A-Za-z_]\w*)")
ATTRIBUTE_ASSIGN_RE = re.compile(r"this\.attributes(?:\[['\"][^'\"]+['\"]\]|\.[A-Za-z_]\w*)\s*=")
VARIABLE_ASSIGN_RE = re.compile(r"this\.variables(?:\[['\"][^'\"]+['\"]\]|\.[A-Za-z_]\w*)\s*=")
MEMORY_ASSIGN_RE = re.compile(r"this\.memory(?:\[['\"][^'\"]+['\"]\]|\.[A-Za-z_]\w*)\s*=")
STATE_ASSIGN_RE = re.compile(r"\bthis\.state\s*=")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_strings(item)


def iter_actions(model):
    states = model.get("states", {})
    for state_name, state in states.items():
        for hook_name, actions in state.get("actions", {}).items():
            for action in actions:
                yield f"states.{state_name}.actions.{hook_name}", action

    transitions = model.get("transitions", {})
    for transition_name, transition in transitions.items():
        for action in transition.get("actions", []):
            yield f"transitions.{transition_name}.actions", action

    behaviors = model.get("behaviors", {})
    for behavior_name, behavior in behaviors.items():
        for action in behavior.get("actions", []):
            yield f"behaviors.{behavior_name}.actions", action

    schedules = model.get("schedules", {})
    for schedule_name, schedule in schedules.items():
        for action in schedule.get("actions", []):
            yield f"schedules.{schedule_name}.actions", action


def add_error(errors, message):
    errors.append(message)


def validate_top_level(model, errors):
    if model.get("$schema") != "https://agent-studio.io/schema/v2":
        add_error(errors, "Top-level $schema must be https://agent-studio.io/schema/v2")

    metadata = model.get("metadata", {})
    if not metadata.get("name"):
        add_error(errors, "metadata.name is required")
    if not metadata.get("title"):
        add_error(errors, "metadata.title is required")

    if not any(key in model for key in ("attributes", "variables", "services", "goals")):
        add_error(errors, "Model must contain at least one of attributes, variables, services, or goals")


def validate_rule_references(model, errors):
    rules = model.get("rules", {})

    for var_name, variable in model.get("variables", {}).items():
        x_rules = variable.get("x-rules", {})
        for phase in ("pre", "post"):
            for item in x_rules.get(phase, []):
                rule_name = item.get("rule")
                if rule_name and rule_name not in rules:
                    add_error(errors, f"variables.{var_name}.x-rules.{phase} references missing rule {rule_name}")

    for service_name, service in model.get("services", {}).items():
        service_rules = service.get("rules", {})
        for phase in ("pre", "post"):
            for item in service_rules.get(phase, []):
                rule_name = item.get("rule")
                if rule_name and rule_name not in rules:
                    add_error(errors, f"services.{service_name}.rules.{phase} references missing rule {rule_name}")


def validate_field_references(model, errors):
    defined = {
        "attributes": set(model.get("attributes", {}).keys()),
        "variables": set(model.get("variables", {}).keys()),
        "derivedProperties": set(model.get("derivedProperties", {}).keys())
    }

    for section_name in (
        "derivedProperties",
        "rules",
        "functions",
        "services",
        "states",
        "transitions",
        "behaviors",
        "events",
        "alarms",
        "schedules",
        "goals",
        "decisionPolicies",
        "memory",
        "plans"
    ):
        section = model.get(section_name, {})
        for item_name, item in section.items():
            for text in iter_strings(item):
                for scope, name in REFERENCE_RE.findall(text):
                    if name not in defined[scope]:
                        add_error(errors, f"{section_name}.{item_name} references missing {scope}.{name}")

    for prop_name, derived in model.get("derivedProperties", {}).items():
        for dependency in derived.get("x-dependOn", []):
            if (
                dependency not in defined["attributes"]
                and dependency not in defined["variables"]
                and dependency not in defined["derivedProperties"]
            ):
                add_error(errors, f"derivedProperties.{prop_name}.x-dependOn references unknown field {dependency}")


def validate_event_and_service_references(model, errors):
    events = model.get("events", {})
    services = model.get("services", {})

    for transition_name, transition in model.get("transitions", {}).items():
        trigger = transition.get("trigger", {})
        if trigger.get("type") == "event":
            event_name = trigger.get("name")
            if event_name not in events:
                add_error(errors, f"transitions.{transition_name}.trigger references missing event {event_name}")

    for behavior_name, behavior in model.get("behaviors", {}).items():
        trigger = behavior.get("trigger", {})
        if trigger.get("type") == "event":
            event_name = trigger.get("name")
            if event_name not in events:
                add_error(errors, f"behaviors.{behavior_name}.trigger references missing event {event_name}")

    for location, action in iter_actions(model):
        action_type = action.get("type")
        if action_type == "triggerEvent":
            event_name = action.get("name")
            if event_name not in events:
                add_error(errors, f"{location} references missing event {event_name}")
        if action_type == "invokeService":
            service_name = action.get("name")
            if service_name not in services:
                add_error(errors, f"{location} references missing service {service_name}")

    for policy_name, policy in model.get("decisionPolicies", {}).items():
        plan_name = policy.get("plan")
        if plan_name and plan_name not in model.get("plans", {}):
            add_error(errors, f"decisionPolicies.{policy_name} references missing plan {plan_name}")

        for goal_id in policy.get("goals", []):
            if goal_id not in model.get("goals", {}):
                add_error(errors, f"decisionPolicies.{policy_name} references missing goal {goal_id}")

        for slot in policy.get("memorySlots", []):
            if slot not in model.get("memory", {}):
                add_error(errors, f"decisionPolicies.{policy_name} references missing memory slot {slot}")

        for trigger in policy.get("escalateWhen", []):
            if trigger.get("type") == "event":
                event_name = trigger.get("name")
                if event_name not in events:
                    add_error(errors, f"decisionPolicies.{policy_name} escalates on missing event {event_name}")

    for plan_name, plan in model.get("plans", {}).items():
        for service_name in plan.get("allowedServices", []):
            if service_name not in services:
                add_error(errors, f"plans.{plan_name} references missing service {service_name}")


def validate_state_machine(model, errors):
    states = model.get("states", {})
    transitions = model.get("transitions", {})

    if transitions and not states:
        add_error(errors, "transitions are defined but states are missing")

    initial_states = [name for name, state in states.items() if state.get("initialState") is True]
    if states and len(initial_states) != 1:
        add_error(errors, f"Exactly one initialState is required, found {len(initial_states)}")

    for transition_name, transition in transitions.items():
        from_state = transition.get("from")
        to_state = transition.get("to")
        if from_state not in states:
            add_error(errors, f"transitions.{transition_name}.from references missing state {from_state}")
        if to_state not in states:
            add_error(errors, f"transitions.{transition_name}.to references missing state {to_state}")


def validate_functions_are_pure(model, errors):
    for function_name, function in model.get("functions", {}).items():
        script = function.get("script", "")
        if ATTRIBUTE_ASSIGN_RE.search(script):
            add_error(errors, f"functions.{function_name} writes this.attributes, which is not allowed")
        if VARIABLE_ASSIGN_RE.search(script):
            add_error(errors, f"functions.{function_name} writes this.variables, which is not allowed")
        if MEMORY_ASSIGN_RE.search(script):
            add_error(errors, f"functions.{function_name} writes this.memory, which is not allowed")
        if STATE_ASSIGN_RE.search(script):
            add_error(errors, f"functions.{function_name} writes this.state, which is not allowed")


def main():
    if len(sys.argv) != 2:
        print("Usage: validate_agent_model.py <model.json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    model = load_json(path)
    errors = []

    validate_top_level(model, errors)
    validate_rule_references(model, errors)
    validate_field_references(model, errors)
    validate_event_and_service_references(model, errors)
    validate_state_machine(model, errors)
    validate_functions_are_pure(model, errors)

    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        sys.exit(1)

    print(f"{path.name} validation passed")


if __name__ == "__main__":
    main()
