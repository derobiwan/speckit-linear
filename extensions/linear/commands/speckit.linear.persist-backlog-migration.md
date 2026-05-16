---
description: Convert a hand-curated tasks.md into Linear task issues + milestones after /speckit.taskstoissues.
---

# /speckit.linear.persist_backlog_migration

After-hook for `/speckit.taskstoissues`. Two-phase write
(milestones-before-tasks).

**Phase A** — for each `## Phase N: …` header in the source tasks.md:

- Call `mcp__claude_ai_Linear__save_milestone` with name
  `{NNN}: Phase N: …`.

**Phase B** — for each task line beneath a phase header:

- Parse the task line into title, ID, `[P]`, `[US?]` markers, and
  description.
- Call `mcp__claude_ai_Linear__save_issue`:
  - **title**: `T{NNN} [P?] [US?] {Description}` (preserve markers
    verbatim — this is a migration, not a rewrite)
  - **labels**: `speckit:task` + `feature:{NNN}-{short-name}` +
    `parallelizable` when `[P]` set
  - **project**: the product project
  - **milestone**: the phase milestone from Phase A
  - **description**: the original tasks.md text for that item
    (preserve verbatim)
  - **idempotency_key**: `speckit:taskstoissues:<feature>:<T-id>` so
    re-running updates in place rather than duplicating.

After migration, the local `tasks.md` is no longer the source of
truth. Archive or delete it to prevent future drift (the Linear
issues are now authoritative — Constitution P2).

Echo: milestones created, tasks created vs updated-in-place, product
project name, feature label.
