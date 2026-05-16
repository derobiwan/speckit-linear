---
description: Persist [PLAN], [RESEARCH], [DATA-MODEL], [CONTRACT], [QUICKSTART] issues after /speckit.plan.
---

# /speckit.linear.persist_plan

After-hook for `/speckit.plan`. Create one issue per substantive
artifact via `mcp__claude_ai_Linear__save_issue`. Only create issues
whose content is non-empty (e.g., skip `[CONTRACT]` for purely
internal projects).

| Title                                          | Type label        |
|------------------------------------------------|-------------------|
| `[PLAN] {NNN}: Implementation Plan`            | speckit:plan      |
| `[RESEARCH] {NNN}: Technical Research`         | speckit:research  |
| `[DATA-MODEL] {NNN}: Entity Definitions`       | speckit:data-model|
| `[CONTRACT] {NNN}: API Contract`               | speckit:contract  |
| `[QUICKSTART] {NNN}: Integration Guide`        | speckit:quickstart|

Every issue gets:

- **labels**: `<type label>` + `feature:{NNN}-{short-name}`
- **project**: the product project (resolved by before-hook)
- **idempotency_key**: `speckit:plan:<feature>:<type>` so retries
  update-in-place rather than duplicating.

After creation, echo all five issue links to the user (suppressing any
that were skipped).
