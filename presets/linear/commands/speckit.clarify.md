---
description: Resolve spec ambiguities and integrate clarifications into the Linear [SPEC] issue.
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

**This skill = Step 3** of the canonical sequence.

**Required predecessor(s)**: `[SPEC]` issue must exist (`/speckit.specify` or `/speckit.baseline`).

**Successor(s)**: `/speckit.plan`.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_clarify hook)

`speckit.linear.resolve_active_feature` locates the `[SPEC]` issue and
reads its description. Abort if missing — no local-file fallback
(Constitution P2).

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_clarify hook)

`speckit.linear.persist_clarifications` updates the spec issue:

1. After EACH accepted Q/A, call `mcp__claude_ai_Linear__save_issue` (with
   the existing issue ID, which performs an in-place update) to atomically
   overwrite the description with:
   - A `## Clarifications` section (created if absent)
   - A `### Session YYYY-MM-DD` subheading for today
   - A `- Q: … -> A: …` bullet appended after each accepted answer
   - Any in-section edits (Functional Requirements, Data Model, etc.)
     derived from the answer

   Incremental save after each answer minimizes blast radius if a later
   step fails (no half-applied state lost).

2. Update the Requirements Quality `[CHECKLIST]` issue if the
   clarification resolved a previously failing item — replace the
   description via `save_issue` with the new pass/fail state.

Report: questions asked, sections touched, coverage summary table, next
step (`/speckit.plan` or another `/speckit.clarify` pass).
