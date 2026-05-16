---
description: Relabel a legacy Linear backlog with the dual speckit:* + feature:NNN-name convention (idempotent, in-place).
---

# /speckit.linear.migrate

Ports v0.5.1 backlog-migration behaviour into the namespaced extension
layout. Implemented by `extensions/linear/scripts/linear_migrate.py`
(T062). Also routed as an alias from plain `/speckit.migrate` via the
Linear preset (FR-010).

## User Input

```text
$ARGUMENTS
```

Expected `$ARGUMENTS`: a kebab-case feature short name (e.g.,
`user-auth`) and a list of Linear issue ids to relabel. The runtime
resolves the feature label automatically (creating
`feature:NNN-<short>` if it doesn't exist, where `NNN` is the next
available three-digit prefix).

## Behavior

1. Use `mcp__claude_ai_Linear__list_issue_labels` + the existing
   `feature:NNN-*` numbering to resolve the canonical feature label
   for the given short name. Create it via
   `mcp__claude_ai_Linear__create_issue_label` if missing.
2. For each legacy issue id supplied:
   - Fetch the current label set via
     `mcp__claude_ai_Linear__list_issues`.
   - If the issue already wears both `speckit:task` and the resolved
     `feature:NNN-<short>` label, skip it (idempotency).
   - Otherwise add both labels (preserving any pre-existing labels)
     via `mcp__claude_ai_Linear__save_issue` with the existing id.
3. Print a structured diff: relabeled issues, skipped issues, and
   the canonical feature label name.

## Constitution invariants enforced here

- **P1** — no patch to `src/specify_cli/`.
- **P2** — Linear-first storage; on MCP failure the wrapper raises
  rather than writing locally.
- **FR-010** — this script powers both `/speckit.linear.migrate` and
  the plain `/speckit.migrate` alias routed through the Linear preset.

## Echo

```text
[linear] migrate: relabeled=<N> skipped=<M> feature=<feature:NNN-name>
```
