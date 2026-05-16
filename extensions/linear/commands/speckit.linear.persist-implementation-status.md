---
description: Update task issue statuses as work proceeds in /speckit.implement.
---

# /speckit.linear.persist_implementation_status

After-hook for `/speckit.implement`. Updates Linear status incrementally
as work moves through tasks; runs at multiple checkpoints, not just at
end-of-phase.

For each task transition the agent performs:

1. Call `mcp__claude_ai_Linear__list_issue_statuses` once per session
   to look up the workspace's actual state IDs (don't hardcode state
   names — different workspaces use different names like "In Progress"
   vs. "Doing" vs. "Working").

2. On **picking up** a task:
   - Call `mcp__claude_ai_Linear__save_issue(id=<task>, state=<in-progress-state>)`.

3. On **completing** a task (all acceptance criteria met + tests pass):
   - Call `save_issue(id=<task>, state=<done-state>)`.
   - Append a comment via `mcp__claude_ai_Linear__save_comment`
     linking the commit SHA(s): `Implemented in <repo>@<sha>`.

4. On **blocking** (cannot proceed without external input):
   - Leave the task in in-progress.
   - Append a comment describing the blocker.
   - DO NOT silently skip.

Use `idempotency_key` of the form
`speckit:implement:<feature>:<T-id>:<transition>` so retries do not
double-transition.

Constitution P4 reminder: never transition to done while tests fail
or the implementation is partial. Pre-commit hooks
(gitleaks/ruff/pytest) enforce this gate.
