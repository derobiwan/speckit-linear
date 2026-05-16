---
description: Create or update a [CHECKLIST] issue after /speckit.checklist.
---

# /speckit.linear.persist_checklist

After-hook for `/speckit.checklist`. Multiple checklists per feature are
supported (Q1 clarification — one-issue-per-artifact, per domain).

1. Compose the title: `[CHECKLIST] {NNN}: {Domain} Quality Validation`
   (e.g., `[CHECKLIST] 001: Security Quality Validation`).

2. Locate an existing matching checklist via
   `mcp__claude_ai_Linear__list_issues(label="feature:{NNN}-{short-name}", label="speckit:checklist")`
   filtered by title prefix. If found, update in place via
   `mcp__claude_ai_Linear__save_issue(id=<existing>, description=<new body>)`.

3. Otherwise create via `save_issue`:
   - **labels**: `speckit:checklist` + `feature:{NNN}-{short-name}`
   - **project**: the product project
   - **description**: the generated checklist content (CHK001 onwards)

Use `idempotency_key` `speckit:checklist:<feature>:<domain>` so a
re-run for the same domain updates rather than duplicates.

Echo the checklist issue link, total items, and the focus areas.
