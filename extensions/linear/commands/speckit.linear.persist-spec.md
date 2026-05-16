---
description: Persist the [SPEC] issue + feature label + initial requirements-quality checklist after /speckit.specify.
---

# /speckit.linear.persist_spec

After-hook for `/speckit.specify`. The wrap-strategy preset has just
produced the spec content; persist it to Linear.

1. Ensure the feature label exists:
   - Call `mcp__claude_ai_Linear__list_issue_labels`, compute next
     `NNN` by scanning existing `feature:NNN-*` labels.
   - Call `mcp__claude_ai_Linear__create_issue_label` with name
     `feature:NNN-<short-name>`.

2. Create the spec issue via `mcp__claude_ai_Linear__save_issue`:
   - **title**: `[SPEC] {NNN}: {Feature Name}`
   - **labels**: `speckit:spec` + `feature:{NNN}-{short-name}`
   - **project**: the resolved product project
   - **description**: the full spec markdown (Linear accepts real
     newlines — do NOT escape them as `\n`)

3. Create the initial quality checklist via `save_issue`:
   - **title**: `[CHECKLIST] {NNN}: Requirements Quality`
   - **labels**: `speckit:checklist` + `feature:{NNN}-{short-name}`
   - **project**: same product project
   - **description**: the standard checklist body

4. Echo the issue links to the user.

Pass `idempotency_key` of the form
`speckit:specify:<sha256-12 of spec content>` so retries do not create
duplicates.
