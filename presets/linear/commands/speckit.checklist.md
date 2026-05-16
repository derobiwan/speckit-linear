---
description: Generate a requirements-quality checklist as a Linear [CHECKLIST] issue.
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

**This skill = Step 5** of the canonical sequence.

**Required predecessor(s)**: `[SPEC]` issue must exist (and ideally `[PLAN]` too). May run at multiple phases.

**Successor(s)**: `/speckit.tasks` (when used in the main flow).

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_checklist hook)

`speckit.linear.resolve_active_feature` locates the `[SPEC]` (required)
and `[PLAN]` (optional) issues to derive context. Multiple
`[CHECKLIST]` issues per feature are supported (Q1 clarification:
one-issue-per-artifact, including per-domain checklists). Each
domain-specific checklist becomes its own issue.

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_checklist hook)

`speckit.linear.persist_checklist` creates the issue via
`mcp__claude_ai_Linear__save_issue`:

- **Title**: `[CHECKLIST] {NNN}: {Domain} Quality Validation`
- **Labels**: `speckit:checklist`, `feature:{NNN}-{short-name}`
- **Project**: the product project
- **Description**: the full checklist content (CHK001 onwards, grouped
  by quality dimension)

When the user re-runs checklist validation later, locate the existing
checklist issue by title prefix and dual-label match, then update its
description in place via `save_issue(id=…)` to record pass/fail status.

Report: focus areas, item count, depth level, audience, checklist issue
link.
