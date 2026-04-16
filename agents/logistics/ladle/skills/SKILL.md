---
name: scheduling-rule-maker
description: A specialized tool for configuring cold rolling production scheduling rules. It uses a "Subject-Attribute-Condition-Action" (LHS-RHS) logic to define physical constraints, process specifications, and optimization goals. Use this skill when you need to create, update, or validate scheduling rules for steel production units.
---

# Scheduling Rule Maker

This skill provides a structured framework for defining scheduling rules in the steel industry, specifically for cold rolling mills.

## Core Concepts

- **LHS (Left Hand Side)**: The condition or trigger for the rule.
- **RHS (Right Hand Side)**: The action or consequence (Veto or Score).
- **Physical Attributes**: Immutable characteristics of a coil (Weight, Width, etc.).
- **Planning Attributes**: Dynamic roles assigned during scheduling (Sequence No, Plan Role).

## Workflow for Creating a Rule

1. **Identify the Scope**: Is it a single coil check, a pairwise (adjacent) check, or a rolling unit aggregation?
2. **Define the LHS**: Use attributes and operators (>, <, =, In, AND, OR) to build the condition.
3. **Define the RHS**:
   - **Veto**: Hard constraint (Illegal/Forbidden).
   - **Score**: Soft constraint (Reward/Penalty).
4. **Set Priority**: Critical, High, Normal, or Low.

## Rule Categories

- **Compatibility Rules**: Physical vs Planning attribute alignment.
- **Sequence Rules**: Continuity between adjacent coils.
- **Aggregation Rules**: Statistical limits for the whole rolling unit.

## Reference Files

- [data-model.md](references/data-model.md): Detailed attribute definitions.
- [templates.md](references/templates.md): Rule category templates and logic examples.
- [scoring.md](references/scoring.md): Scoring mechanism and priority levels.
