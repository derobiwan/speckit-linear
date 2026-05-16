---
description: Create the technical plan and supporting artifacts, persisted to Linear.
strategy: wrap
---

## Workflow Position (canonical Spec Kit sequence — MANDATORY)

The Spec Kit lifecycle MUST be executed in this order on every feature, with no skipped steps:

| Step | Command | Required? | Gating |
|------|---------|-----------|--------|
| 1 | `/speckit.constitution` | Required (one-time per repo) | none |
| 2 | `/speckit.specify` *(or `/speckit.baseline` for brownfield)* | Required | constitution |
| 3 | `/speckit.clarify` | Optional — runs before plan | specify |
| 4 | `/speckit.plan` | Required | specify (+ clarify if invoked) |
| 5 | `/speckit.checklist` | Optional — may repeat after plan | plan |
| 6 | `/speckit.tasks` | Required | plan (+ checklist if invoked) |
| 7 | `/speckit.analyze` | Optional — runs before implement | tasks |
| 8 | `/speckit.implement` | Required | tasks (+ analyze if invoked) |

**This skill = Step 4** of the canonical sequence.

**Required predecessor(s)**: `[SPEC]` issue must exist. If `/speckit.clarify` was started, it must be completed before invoking plan.

**Successor(s)**: `/speckit.checklist` *(optional)* or `/speckit.tasks`.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_plan hook)

`speckit.linear.resolve_active_feature` resolves the active feature:

1. Follow the "Find Active Feature" pattern from `.specify/config/linear.md`.
2. Use `mcp__claude_ai_Linear__list_issues(project=<product>, label="feature:NNN-name")`.
3. Filter by title prefix to locate the `[SPEC]` issue (read via `get_issue`).
4. Locate the constitution by listing projects for `speckit-constitution`,
   then fetching the `speckit:constitution` issue.
5. Abort if either is missing — do NOT proceed to plan generation without
   a spec + constitution (Constitution P2 — no local-file fallback).

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_plan hook)

`speckit.linear.persist_plan` creates the plan-suite issues via
`mcp__claude_ai_Linear__save_issue`. Use dual labels (`speckit:*` +
`feature:{NNN}-{short-name}`) on every issue. Only create issues whose
artifact has substantive content:

| Issue                                          | Labels                                 |
| ---------------------------------------------- | -------------------------------------- |
| `[PLAN] {NNN}: Implementation Plan`            | `speckit:plan` + feature label         |
| `[RESEARCH] {NNN}: Technical Research`         | `speckit:research` + feature label     |
| `[DATA-MODEL] {NNN}: Entity Definitions`       | `speckit:data-model` + feature label   |
| `[CONTRACT] {NNN}: API Contract`               | `speckit:contract` + feature label     |
| `[QUICKSTART] {NNN}: Integration Guide`        | `speckit:quickstart` + feature label   |

Run agent-context update (`update-agent-context.sh --plan-file <tmp>`)
against a *temporary* local file, then discard. Persistent state lives in
Linear.

Report: product project, feature label, list of created issue links,
next-step command (`/speckit.tasks` or `/speckit.checklist`).
