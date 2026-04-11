# Agent Studio Config Workbench Design

- Date: 2026-04-11
- Scope: Agent Studio desktop-first configuration workspace
- Status: Draft approved in conversation, written for review

## Goal

Design a configuration workspace for Agent Studio with a stable left-to-right flow:

1. Menu
2. Model list
3. Instance list
4. Instance detail

The workspace should feel like a compact professional control console rather than a generic admin page. It should optimize for fast scanning on the left and focused editing on the right.

## Product Intent

The key interaction principle is single responsibility per column:

- The menu chooses the management domain.
- The model list chooses the current model.
- The instance list chooses the current instance under that model.
- The detail panel edits or inspects the selected instance.

This removes ambiguity from the navigation path and keeps the user oriented at every step.

## Information Architecture

### Primary navigation

The leftmost column contains only first-level destinations:

- `Models`
- `Data`
- `Events`
- `Prefs`

Notes:

- The menu is intentionally ultra narrow.
- It should only be wide enough to fit short labels.
- It should not contain nested tree navigation.
- Active state must be obvious through a filled background block, not only text color.
- The header area should be minimal, such as `AS` or `Studio`.

### Core workspace flow

When the user is in `Models`, the remaining three columns are:

- `Models` list
- `Instances` list for the selected model
- `Instance Detail` for the selected instance

This is a fixed four-pane desktop layout. The structure does not collapse conceptually while the user is working; only the selected entities change.

## Layout

### Desktop layout

Recommended desktop column order:

1. Ultra-narrow menu
2. Narrow model list
3. Narrow instance list
4. Wide detail editor

Recommended relative proportions:

- Menu: minimum comfortable readable width
- Model list: slim browsing column
- Instance list: slim operational column
- Detail: dominant editing surface

The working principle is that the rightmost detail panel receives the majority of horizontal space.

### Mobile and narrow widths

The desktop four-pane layout is not preserved as-is on narrow screens.

Responsive strategy:

- Keep the domain menu accessible.
- Show one list pane at a time when space is tight.
- Open the detail area as the main surface after selection, with list return handled by back navigation or drawer behavior.

This avoids unusable compressed columns on smaller screens.

## Column Specifications

### 1. Menu column

Purpose:

- Switch between top-level configuration domains.

Content:

- Minimal brand marker
- Four first-level navigation items

Rules:

- No secondary tree
- Centered or tightly aligned labels
- Compact vertical rhythm
- Strong active fill

### 2. Model list column

Purpose:

- Choose which model is currently active in the workspace.

Each row contains:

- Model name
- Short usage or purpose tag
- Instance count

Header content:

- Lightweight title such as `Models 12`
- Small `+ New` action

Rules:

- Do not overload this column with operational status badges.
- Keep it focused on identity and scope, not live runtime state.
- Selected row uses full-row highlight.

### 3. Instance list column

Purpose:

- Show instances under the selected model.

Each row contains:

- Instance name
- Runtime status
- Deployment region

Rules:

- This is where operational status belongs.
- Selected state should be stronger than the selected state in the model list because it directly drives the editor.
- Rows should remain compact and scannable.

### 4. Instance detail column

Purpose:

- Inspect and edit the currently selected instance.

Header content:

- Instance name
- Parent model reference
- Compact status summary
- `Reset` and `Save` actions

Body structure:

- Thin tab bar
- Default tab is `Overview`

Recommended tabs:

- `Overview`
- `Bindings`
- `Runtime`
- `JSON`

Tab responsibilities:

- `Overview`: common editable fields
- `Bindings`: associated relationships and mappings
- `Runtime`: current runtime values or semi-read-only operational information
- `JSON`: advanced raw editing for power users

## Visual Direction

### Tone

Use a light professional control-console style:

- Cool gray-blue surfaces
- Thin dividers between panes
- Very light background separation
- Minimal visual noise

Avoid:

- Heavy card stacking
- Large decorative headers
- Generic admin-table look

### Density

Use medium-high density with intentional asymmetry:

- Leftmost panes are denser because they are for navigation and scanning.
- Rightmost pane is more spacious because it is for reading and editing.

This means density should gradually decrease from left to right.

### Hierarchy

Hierarchy should come from:

- Alignment
- Spacing
- Weight
- Contrast
- Selection treatment

Not from oversized typography.

Selection rules:

- Model selected state: clear but moderate
- Instance selected state: stronger than model selected state
- Active menu state: strongest navigation indicator in the left rail

## Interaction Notes

### Selection behavior

- Selecting a model refreshes the instance list column.
- Selecting an instance refreshes the detail column.
- Selection should not navigate the user away from the workspace pattern.

### Editing behavior

- Save and reset remain anchored in the detail header.
- Tabs should not push primary actions off screen.
- The detail layout should keep the most edited fields above the fold.

### Discoverability

- The user should understand the drill-down order without explanation.
- Each column title should make the current step obvious.

## Error Handling and Empty States

### Empty model state

If there are no models:

- Show a guided empty state in the model column
- Offer a `+ New` path
- Keep the rest of the layout visible but inactive

### Empty instance state

If a model has no instances:

- Keep the model selected
- Show an empty state in the instance column
- Disable or placeholder the detail area until an instance exists

### Missing selection state

If no instance is selected:

- Keep the detail pane visible
- Show a placeholder that explains the next step

## Implementation Constraints

- Follow existing Ant Design and current project layout patterns where practical.
- Preserve the current route-based model and instance detail behavior, but adapt the UI composition to the fixed four-pane workspace.
- The design should remain desktop-first.
- The menu labels may use shortened names in the narrow rail if needed for fit and readability.

## Testing Expectations

Implementation should verify:

- Correct four-pane rendering for the `Models` workspace
- Stable selection flow from model to instance to detail
- Correct empty states for no models and no instances
- Responsive fallback behavior for narrow widths
- Save and reset actions remain reachable in the detail panel

## Recommended Direction

Adopt the compact four-pane workbench with:

- Ultra-narrow left navigation
- Slim model list
- Slim instance list
- Wide instance editor

This is the clearest match to the intended user flow and gives the configuration editor the most valuable screen area.
