---
description: Analyze an existing source directory and persist a [SPEC] issue describing the discovered features.
---

# /speckit.linear.baseline

Generates a baseline `[SPEC]` issue in Linear by scanning an existing
source code directory. Implemented by
`extensions/linear/scripts/linear_baseline.py` (T064). Also routed as
an alias from plain `/speckit.baseline` via the Linear preset
(FR-010).

## User Input

```text
$ARGUMENTS
```

Expected `$ARGUMENTS`: a path to the project root to analyze, plus a
kebab-case feature short name (e.g., `reverse-engineered-arch`). The
runtime resolves the feature label automatically.

## Behavior

1. Walk `source_dir/src/*` — each immediate subdirectory containing
   at least one recognized source file (`.py`, `.ts`, `.tsx`, `.js`,
   `.jsx`, `.go`, `.java`, `.rs`) becomes a discovered feature. Hidden
   directories and `_internal/` are skipped.
2. Resolve (or create) the canonical `feature:NNN-<short>` label via
   `mcp__claude_ai_Linear__create_issue_label` (numbering is automatic).
3. Persist a single `[SPEC]` issue via
   `mcp__claude_ai_Linear__save_issue` with dual labels
   (`speckit:spec` + the feature label). The body lists every
   discovered feature with its relative path.
4. On re-run with the same source: look up the existing `[SPEC]`
   issue by feature label and `save_issue` with its id so the update
   lands in place (idempotency).

## Constitution invariants enforced here

- **P1** — no patch to `src/specify_cli/`.
- **P2** — Linear-first storage; the script never writes the spec
  body to disk on MCP failure.
- **FR-010** — this script powers both `/speckit.linear.baseline` and
  the plain `/speckit.baseline` alias routed through the Linear
  preset.

## Echo

```text
[linear] baseline: features=<N> spec=<issue-id> feature=<feature:NNN-name>
```
