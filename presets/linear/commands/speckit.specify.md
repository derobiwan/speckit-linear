---
description: Create or update the feature specification, persisting to Linear instead of local files.
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

**This skill = Step 2** of the canonical sequence.

**Required predecessor(s)**: Constitution must exist (`/speckit.constitution`).

**Successor(s)**: `/speckit.clarify` *(optional)* or `/speckit.plan`.

**Prerequisite gate (MANDATORY)**: Before executing the body of this skill,
verify each required predecessor produced its expected Linear issue (under the
Linear preset) or local artifact (under any other preset). If a required
predecessor artifact is missing, abort with a clear error instructing the user
to run the missing skill first. Steps MUST NOT be skipped, reordered, or
silently substituted, even if the user requests it — instead, surface the
violation and ask for explicit confirmation to deviate (deviation requires the
user to acknowledge the downstream rework risk in writing).

---

## Linear-First Storage — Pre-Execution

> This preset replaces local-file storage with Linear-as-storage-backend.
> All artifact reads and writes use the official Linear MCP server
> (`mcp__linear__*`). Constitution P2: NEVER fall back to local files on
> MCP failure — abort with a clear error so the user can remediate.

**Before generating the spec**, run the `before_specify` hook
(`speckit.linear.resolve_product_project`) to:

1. Read `.specify/config/linear.md` for the product project name.
2. Locate the product project via `mcp__claude_ai_Linear__list_projects` /
   create it via `mcp__claude_ai_Linear__save_project` if absent.
3. Determine the next feature number by scanning existing
   `feature:NNN-*` labels (use `mcp__claude_ai_Linear__list_issue_labels`).
4. Create the `feature:{NNN}-{short-name}` label via
   `mcp__claude_ai_Linear__create_issue_label`.

---

{CORE_TEMPLATE}

---

## Linear-First Storage — Post-Execution (after_specify hook)

After generating the spec content, persist via
`speckit.linear.persist_spec`:

1. Create the spec issue via `mcp__claude_ai_Linear__save_issue`:
   - **Title**: `[SPEC] {NNN}: {Feature Name}`
   - **Labels**: `speckit:spec`, `feature:{NNN}-{short-name}`
   - **Project**: the product project resolved in the pre-hook
   - **Description**: full spec markdown (Linear MCP accepts raw newlines —
     do NOT escape them)

2. Create the spec-quality checklist issue:
   - **Title**: `[CHECKLIST] {NNN}: Requirements Quality`
   - **Labels**: `speckit:checklist`, `feature:{NNN}-{short-name}`
   - **Project**: same product project
   - **Description**: the standard requirements-quality checklist content

3. Report to the user:
   - Product project name
   - Feature label
   - Spec issue link (returned by `save_issue`)
   - Checklist issue link
   - Suggested next command (`/speckit.clarify` or `/speckit.plan`)

**Constitution P2 reminder**: If any MCP call fails after bounded retry,
the operation aborts. Do not attempt local-file fallback.
