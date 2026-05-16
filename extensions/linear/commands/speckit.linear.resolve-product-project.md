---
description: Locate or create the product project in Linear before /speckit.specify runs.
---

# /speckit.linear.resolve_product_project

Before-hook for `/speckit.specify`. Steps:

1. Read `.specify/config/linear.md` for the **product project name**.
   - If the line is a placeholder or empty, ask the user for the name
     and rewrite the config line with their answer (this is a one-time
     setup).

2. Call `mcp__claude_ai_Linear__list_projects` with a name filter.
   - If a project with the exact (case-insensitive) name exists, use it.
   - Otherwise call `mcp__claude_ai_Linear__save_project` to create it
     with that name and description "Spec Kit product project — all
     feature artifacts persist here."

3. Cache the resolved project ID in the calling agent's context so
   subsequent calls in the same workflow do not re-list.

## Constitution P2 — no local-file fallback

If the Linear MCP server is unreachable after the bounded retry window,
abort the entire `/speckit.specify` call. Do NOT fall back to writing
the spec to `specs/NNN-name/spec.md`.
