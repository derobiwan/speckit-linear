---
description: Create or amend the project constitution, persisted in the speckit-constitution Linear project.
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

**This skill = Step 1** of the canonical sequence.

**Required predecessor(s)**: *(none — this is the first step in the lifecycle)*

**Successor(s)**: `/speckit.specify` (or `/speckit.baseline` for brownfield).

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution (before_constitution hook)

`speckit.linear.resolve_constitution_project` locates (or creates) the
dedicated constitution project:

1. `mcp__claude_ai_Linear__list_projects` — search for project named
   `speckit-constitution`.
2. If absent, create via `save_project` with name
   `speckit-constitution` and description "Spec Kit project constitution
   and governance principles".
3. Within that project, locate the issue with label
   `speckit:constitution`. If absent, create a new issue (title:
   `[CONSTITUTION] Project Constitution`, label: `speckit:constitution`)
   with the template structure as initial body.

Read the current description via `get_issue` — that IS the canonical
constitution content (Constitution P2 — Linear is the source of truth).

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_constitution hook)

`speckit.linear.persist_constitution` writes the amended constitution
via `mcp__claude_ai_Linear__save_issue(id=<existing>, description=…)`:

- Update body in place (versioning lives inside the body's "Version /
  Ratified / Last Amended" footer).
- Include the Sync Impact Report HTML comment at the top.
- No new issues created (one constitution issue per project, per
  Constitution P6 single-source-of-truth).

Also apply consistency-propagation updates to runtime agent guidance
files locally (`.claude/commands/*`, `.codex/prompts/*`, etc.) where
applicable. These propagation files are tracked in git but not in Linear
(per `.gitignore` — they are generated from preset+integration on
`specify init`).

Report: new version, bump rationale, files flagged for follow-up,
constitution issue link, suggested commit message.
