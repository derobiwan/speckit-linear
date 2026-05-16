---
description: Generate dependency-ordered task issues + phase milestones in Linear.
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

**This skill = Step 6** of the canonical sequence.

**Required predecessor(s)**: `[PLAN]` issue must exist (`/speckit.plan`).

**Successor(s)**: `/speckit.analyze` *(optional)* or `/speckit.implement`.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_tasks hook)

`speckit.linear.resolve_active_feature` locates:

- The `[PLAN]` issue (required) — abort if missing.
- The `[SPEC]` issue (required for user-story priorities).
- Optional artifacts: `[DATA-MODEL]`, `[CONTRACT]`, `[RESEARCH]`,
  `[QUICKSTART]`.

All reads via `mcp__claude_ai_Linear__list_issues` filtered on the
feature label.

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_tasks hook)

`speckit.linear.persist_tasks` creates the phase structure in Linear:

1. **Milestones** (`mcp__claude_ai_Linear__save_milestone`):
   - `{NNN}: Phase 1: Setup`
   - `{NNN}: Phase 2: Foundational`
   - `{NNN}: Phase 3+`: one per user story (P1, P2, …) in priority order
   - `{NNN}: Final Phase: Polish & Cross-Cutting Concerns`

2. **Task issues** (`mcp__claude_ai_Linear__save_issue` per task):
   - **Title**: `T{NNN} [P?] [US?] {Description}`
   - **Labels**: `speckit:task` + `feature:{NNN}-{short-name}` (always
     both) + `parallelizable` when `[P]` is present
   - **Priority**: P1 → Urgent (1), P2 → High (2), P3 → Medium (3)
   - **Project**: the product project
   - **Milestone**: assigned to the appropriate feature-prefixed phase
     milestone
   - **Description**: file paths, dependencies, user-story ref,
     acceptance criteria

**Idempotency**: pass `idempotency_key` to every `save_issue`/`save_milestone`
call so retries during a transient outage do not double-create. Key format:
`speckit:tasks:{feature}:{T-id}` (per Research R5).

Report counts: total tasks, per-user-story, parallelizable, plus MVP scope
(usually User Story 1) and next command (`/speckit.analyze` or
`/speckit.implement`).
