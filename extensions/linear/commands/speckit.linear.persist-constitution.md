---
description: Write the amended constitution body back to the speckit-constitution issue.
---

# /speckit.linear.persist_constitution

After-hook for `/speckit.constitution`. One constitution issue per
project (Constitution P6 — single source of truth).

1. The before-hook resolved (or created) the
   `[CONSTITUTION] Project Constitution` issue in the
   `speckit-constitution` project.

2. Call `mcp__claude_ai_Linear__save_issue(id=<existing>, description=<new body>)`:
   - **description**: the rendered constitution body (including the
     Sync Impact Report HTML comment at the top + version/ratified/
     last-amended footer).

3. Apply consistency-propagation updates to local runtime agent
   guidance files (e.g., `.claude/commands/*`, `.codex/prompts/*`,
   `.gemini/commands/*`) where applicable. These local files are
   regenerated from the preset+integration on the next
   `specify init`, so they are not the source of truth.

4. Echo:
   - New constitution version
   - Bump rationale (MAJOR/MINOR/PATCH)
   - List of local files requiring follow-up
   - Suggested commit message

Use `idempotency_key`
`speckit:constitution:<sha256-12 of body>` so re-running with the
same body is a no-op.
