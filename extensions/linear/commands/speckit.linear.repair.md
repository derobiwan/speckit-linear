---
description: Reconcile drift between the canonical Linear label set and the live workspace (creates missing speckit:* labels, surfaces malformed feature:* labels).
---

# /speckit.linear.repair

Reconciles the live Linear workspace against the canonical label set
defined in `.specify/config/linear.yml`. Implemented by
`extensions/linear/scripts/linear_repair.py` (T060). Reads
`mcp__claude_ai_Linear__list_issue_labels` and writes via
`mcp__claude_ai_Linear__create_issue_label` only when canonical labels
are missing.

## User Input

```text
$ARGUMENTS
```

## Behavior

1. List every label in the workspace via
   `mcp__claude_ai_Linear__list_issue_labels`.
2. For each `speckit:<type>` in the canonical set
   (`spec`, `plan`, `research`, `data-model`, `contract`, `quickstart`,
   `checklist`, `task`, `constitution`):
   - If the label is missing, create it via
     `mcp__claude_ai_Linear__create_issue_label`, using the canonical
     color from `linear-config.yml`.
   - If the label already exists, leave it alone.
3. Scan every existing label that *looks* like a feature label
   (prefix matches `feature:` case-insensitively) and report any that
   do not conform to `feature:NNN-<short-name>` as drift. The repair
   command **never silently rewrites** drift entries — surfacing the
   list and letting the maintainer decide is the contract (Constitution
   P2: no auto-fallback semantics for user data).
4. Print a structured diff:
   - Created labels (with color)
   - Pre-existing labels (skipped — no write)
   - Drift entries (with the reason each was flagged)
5. Re-running on a repaired workspace is a no-op (idempotent).

## Constitution invariants enforced here

- **P1** — no patch to `src/specify_cli/`; this command lives behind
  the Linear extension.
- **P2** — Linear-first storage, no local fallback. MCP failure
  surfaces via the wrapper's `LinearMcpExhaustedError`; the command
  never writes to disk on failure.

## Echo

After completion the command echoes a one-line summary:

```text
[linear] repair: created=<N> existing=<M> drift=<K>
```

…followed by the structured diff sections.
