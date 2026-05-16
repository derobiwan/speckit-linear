---
description: Update the [SPEC] issue with clarification answers after each Q&A in /speckit.clarify.
---

# /speckit.linear.persist_clarifications

After-hook for `/speckit.clarify`. Run AFTER each accepted Q/A (not at
the end) so a network blip doesn't lose accumulated state.

For each accepted clarification:

1. Take the current spec body (in-memory copy).
2. Ensure `## Clarifications` heading exists, with a
   `### Session YYYY-MM-DD` subheading for today.
3. Append `- Q: <question> -> A: <answer>` under the session heading.
4. Apply the clarification to the appropriate sections (Functional
   Requirements, Data Model, etc.) per the inline rules from
   `/speckit.clarify`.
5. Call `mcp__claude_ai_Linear__save_issue(id=<spec-issue-id>, description=<new body>)`
   to atomically overwrite.

If a related `[CHECKLIST] {NNN}: Requirements Quality` issue exists,
update its description via `save_issue(id=…)` to reflect any items
the clarification resolved.

Use `idempotency_key` of the form
`speckit:clarify:<feature>:<sha256-12 of Q+A>` so re-running the same
clarification update is a no-op rather than a duplicate write.
