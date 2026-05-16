---
description: Convert a hand-curated tasks.md into Linear task issues + milestones (backlog migration).
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

**This skill is *deprecated* under the Linear preset** and exposes no behavior that affects the lifecycle. The sequence still applies to all other skills.

**Required predecessor(s)**: Deprecated under the Linear preset — tasks are already Linear issues.

**Successor(s)**: No-op under Linear; informational only.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_taskstoissues hook)

`speckit.linear.resolve_active_feature` locates the active feature label
(or asks the user if no `feature:NNN-*` label exists yet — this command
is typically run for legacy backlogs where a `[SPEC]` was not authored
through `/speckit.specify`).

Resolve the product project from `.specify/config/linear.md`.

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_taskstoissues hook)

`speckit.linear.persist_backlog_migration` creates Linear artifacts:

1. **Phase milestones**: one per phase header found in the source
   tasks.md (e.g., `## Phase 1: Setup` → milestone
   `{NNN}: Phase 1: Setup`). Use `save_milestone`.

2. **Task issues**: one per task line. Each gets:
   - **Title**: `T{NNN} [P?] [US?] {Description}` (preserving the
     original markers from the source file)
   - **Labels**: `speckit:task` + `feature:{NNN}-{short-name}` +
     `parallelizable` when `[P]` present
   - **Milestone**: derived from the section header the task sits under
   - **Description**: the original tasks.md text for that item
     (preserve verbatim — this is a migration, not a rewrite)

3. **Idempotency**: pass `idempotency_key` of the form
   `speckit:taskstoissues:{feature}:{T-id}` so re-running the command
   updates in-place rather than duplicating.

Constitution P2 reminder: this command is the *only* legitimate path
from local tasks.md to Linear. After migration, the local tasks.md is
no longer the source of truth — delete or archive it to prevent drift.

Report: milestones created, tasks created (and how many were updated
in place via idempotency), product project name.
