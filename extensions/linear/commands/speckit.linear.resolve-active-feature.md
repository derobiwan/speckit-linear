---
description: Locate the active feature label and required artifacts before a speckit command runs.
---

# /speckit.linear.resolve_active_feature

Before-hook for any speckit command that operates on an existing
feature. Resolution order:

1. Read `.specify/config/linear.md` — if it pins
   `feature:NNN-name`, use that.
2. If on a git branch matching `NNN-name`, use the branch name.
3. Otherwise call `mcp__claude_ai_Linear__list_issue_labels` to enumerate
   `feature:*` labels and ask the user which one to use.

After resolving, verify the prerequisite artifact for the calling
command exists:

| Caller         | Required artifact (filter by feature label)  |
|----------------|----------------------------------------------|
| /speckit.clarify  | `[SPEC]` issue                            |
| /speckit.plan     | `[SPEC]` issue + constitution issue       |
| /speckit.tasks    | `[PLAN]` issue                            |
| /speckit.checklist| `[SPEC]` issue                            |
| /speckit.analyze  | `[SPEC]`, `[PLAN]`, and ≥1 task issue     |
| /speckit.implement| ≥1 task issue (label speckit:task)        |
| /speckit.taskstoissues| product project + any tasks.md source |

Use `mcp__claude_ai_Linear__list_issues(label=<feature label>)` and
filter by title prefix to locate each required artifact.

## Constitution P2 — no local-file fallback

If any required artifact is missing, ABORT and instruct the user to
run the prerequisite speckit command. Do NOT fall back to scanning
local files such as `specs/NNN-name/spec.md` — those are not the
source of truth in this preset.

If the Linear MCP server is unreachable after the bounded retry
window (Contract C4: 3 attempts, 1s/2s/4s + ±25% jitter), abort with
a clear error. Do NOT proceed with stale cached data.
