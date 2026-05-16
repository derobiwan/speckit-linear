---
description: Persist phase milestones and task issues with dual labels after /speckit.tasks.
---

# /speckit.linear.persist_tasks

After-hook for `/speckit.tasks`. Two-phase write: milestones first
(tasks reference them), then tasks.

**Phase A — milestones** via `mcp__claude_ai_Linear__save_milestone`:

- `{NNN}: Phase 1: Setup`
- `{NNN}: Phase 2: Foundational`
- One per user story (P1, P2, …) in priority order
- `{NNN}: Final Phase: Polish & Cross-Cutting Concerns`

**Phase B — tasks** via `mcp__claude_ai_Linear__save_issue` (one call
per task; parallelizable up to MCP rate limits):

- **title**: `T{NNN} [P?] [US?] {Description}` (preserve `[P]` and
  `[US?]` markers from the source)
- **labels**: `speckit:task` + `feature:{NNN}-{short-name}` (always
  both); add `parallelizable` when `[P]` is set
- **priority**: P1 → Urgent (1), P2 → High (2), P3 → Medium (3),
  otherwise unspecified
- **project**: the product project
- **milestone**: the matching feature-prefixed phase milestone
- **idempotency_key**: `speckit:tasks:<feature>:<T-id>` so retries
  update-in-place rather than duplicating

Echo total counts (tasks created vs updated-in-place) and the
suggested MVP scope (typically User Story 1).
