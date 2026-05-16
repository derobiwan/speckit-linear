---
description: Post the analysis report as a comment on the [SPEC] issue after /speckit.analyze.
---

# /speckit.linear.persist_analysis_report

After-hook for `/speckit.analyze`. The analyze skill is read-only by
contract — we never modify other issue descriptions here, only append
a comment to the spec issue.

1. Locate the `[SPEC]` issue (already resolved by the before-hook).

2. Call `mcp__claude_ai_Linear__save_comment` with:
   - **issue**: the `[SPEC]` issue ID
   - **body**: the full Markdown report (findings table, coverage
     summary, metrics, recommended next actions)

3. If the user later approves remediations, those updates are written
   to the affected issues separately via `save_issue(id=…)` calls.
   That remediation step is NOT part of this after-hook.

Use `idempotency_key` `speckit:analyze:<feature>:<sha256-12 of report body>`
so a re-run for the same content is a no-op.

Echo the spec issue link and the count of findings by severity.
