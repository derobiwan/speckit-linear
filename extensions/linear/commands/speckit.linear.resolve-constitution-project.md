---
description: Locate or create the speckit-constitution project in Linear before /speckit.constitution runs.
---

# /speckit.linear.resolve_constitution_project

Before-hook for `/speckit.constitution`. Steps:

1. Call `mcp__claude_ai_Linear__list_projects` with name filter
   `speckit-constitution`.

2. If the project does not exist, call
   `mcp__claude_ai_Linear__save_project` to create it with:
   - **name**: `speckit-constitution`
   - **description**: `Spec Kit project constitution and governance principles`

3. Within that project, call
   `mcp__claude_ai_Linear__list_issues(project=<id>, label="speckit:constitution")`
   to locate the constitution issue.

4. If the constitution issue does not exist, prepare to create it in
   the after-hook with the rendered template body.

5. If it does exist, read its description via
   `mcp__claude_ai_Linear__get_issue` — that body is the current
   constitution.

## Constitution P2 — no local-file fallback

If the MCP server is unreachable after the bounded retry window,
abort. Do NOT fall back to `memory/constitution.md` or any other
local path — those files are not the source of truth in this preset.
