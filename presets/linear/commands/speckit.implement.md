---
description: Execute task issues end-to-end, updating Linear status as work progresses.
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

**This skill = Step 8** of the canonical sequence.

**Required predecessor(s)**: Task issues must exist. If `/speckit.analyze` was started, complete it first.

**Successor(s)**: *(none — PR / merge / release happens outside the lifecycle)*.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_implement hook)

`speckit.linear.resolve_active_feature` locates:

- All task issues with label `feature:{NNN}-{short-name}` AND
  `speckit:task` (filter both labels via `list_issues`).
- Phase milestones for the feature (so the implement loop iterates
  phase-by-phase in dependency order).
- The `[PLAN]` and `[CONTRACT]` issues (read-only) for cross-reference.

Read available statuses for the team via
`mcp__claude_ai_Linear__list_issue_statuses` so subsequent transitions
target the workspace's actual state IDs (not hardcoded names).

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_implement hook)

`speckit.linear.persist_implementation_status` updates each task issue
via `mcp__claude_ai_Linear__save_issue(id=…, state=…)` as work proceeds:

1. **When picking up a task**: transition to in-progress state (look up
   the canonical state ID via `list_issue_statuses` and pass `state`).
2. **When completing a task**: transition to done state. Append a brief
   comment via `save_comment` linking the commit SHA(s) that landed the
   work (e.g., `Implemented in <repo>@<sha>`).
3. **When blocked**: leave the task in in-progress and add a comment
   describing the blocker. Do NOT silently skip.

**Idempotency**: pass `idempotency_key` (e.g.,
`speckit:implement:{feature}:{T-id}:transition`) so a retry after a
flaky network does not double-transition.

Constitution P4 reminder: tests must already pass before transitioning
a task to done. The pre-commit hooks (gitleaks, ruff, pytest) gate this
automatically.

Report: per-phase progress (X/Y tasks done), tasks transitioned, blockers
surfaced, next phase.
