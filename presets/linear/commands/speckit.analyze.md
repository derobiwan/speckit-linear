---
description: Cross-artifact consistency analysis; persist results as a comment on the [SPEC] issue.
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

**This skill = Step 7** of the canonical sequence.

**Required predecessor(s)**: Task issues must exist (`/speckit.tasks`).

**Successor(s)**: `/speckit.implement`.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_analyze hook)

`speckit.linear.resolve_active_feature` locates the entire artifact set
in Linear:

- `[SPEC]`, `[PLAN]` — required
- Task issues (titles starting with `T`) — required (analyze runs only
  after `/speckit.tasks`)
- Optional: `[RESEARCH]`, `[DATA-MODEL]`, `[CONTRACT]`, `[CHECKLIST]`
- Constitution: `speckit-constitution` project,
  `speckit:constitution` issue

This skill is STRICTLY READ-ONLY (Constitution P2 still applies for
storage — abort on MCP failure rather than reading stale local cache).

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_analyze hook)

`speckit.linear.persist_analysis_report` writes the report as a comment
on the `[SPEC]` issue via `mcp__claude_ai_Linear__save_comment`:

- **Issue**: the `[SPEC]` issue
- **Body**: the full Markdown report (findings table, coverage summary,
  metrics, remediation queue if any)

Do NOT modify any other issue descriptions (analyze is read-only by
contract). Remediation, if approved by the user, runs as a separate
follow-up that uses `save_issue` on the affected artifact.

Report: total findings by severity, coverage %, recommended next step
(remediate-first vs proceed to `/speckit.implement`).
