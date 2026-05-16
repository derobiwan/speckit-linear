# v0.5.1 backward-compat snapshot — capture procedure

This document describes how to produce `v051-snapshot.json`, the test corpus
used by `tests/backward-compat/test_v051_parity.py` (T046) to enforce
Spec FR-016 and SC-005 — namely, that v1.0.0's Linear issue shape stays
identical to the v0.5.1 fork's.

The snapshot is committed alongside the test. It MUST be re-captured only
when an FR explicitly changes the issue shape; ad-hoc updates defeat the
purpose of the test.

## Inputs

- A Linear workspace where the v0.5.1 fork has been used to produce
  representative artifacts (spec, plan, research, data-model, quickstart,
  contract, checklist, task, constitution).
- A configured Linear MCP server.
- An installed `gitleaks` (the scrubber will produce a clean snapshot).

## Procedure

1. **Pick representatives**. Identify exactly one Linear issue per
   `speckit:<type>` label (9 types). For the multi-checklist case, capture
   2 distinct checklists. The PMO workspace used during this rebuild
   already has representatives at PMO-70..PMO-153 — those are the
   captured corpus.

2. **Fetch raw payloads** via the Linear MCP server. For each Linear
   issue ID:

   ```python
   from extensions.linear.scripts.linear_mcp_client import LinearMcpClientImpl
   # (instantiate per fixtures.linear_config)
   for issue_id in REPRESENTATIVES:
       payload = client.call("mcp__linear__get_issue", id=issue_id)
       store_in_dict(issue_id, payload)
   ```

3. **Filter the payload to the assertion surface**. The parity test compares
   ONLY:

   - `title`
   - `labels` (set of names, order-insensitive)
   - `description` (first 5000 chars; longer descriptions hash-equal beyond that)
   - `priority.value` and `priority.name`
   - `state` (string only — not the full Linear state object)

   Do NOT include: `id`, `identifier`, `url`, timestamps, `createdBy`,
   workspace IDs, team IDs. These are workspace-specific and would defeat
   the snapshot.

4. **Scrub through `redact()`** before writing to disk:

   ```python
   from extensions.linear.scripts.redacting_filter import redact
   for entry in snapshot.values():
       entry["description"] = redact(entry["description"])
   ```

5. **Write `tests/backward-compat/v051-snapshot.json`** with the scrubbed
   filtered payloads keyed by `speckit:<type>` (the canonical key used by
   the parity test).

6. **Validate**: run `gitleaks detect --no-git -p tests/backward-compat/`
   and confirm zero findings. Run `pytest tests/backward-compat/` and
   confirm the parity test loads the snapshot without error (it will fail
   meaningfully when implementation lands and produces different shapes).

## Schema (target shape of `v051-snapshot.json`)

```json
{
  "speckit:spec": {
    "title": "[SPEC] NNN: Feature Name",
    "labels": ["speckit:spec", "feature:NNN-name"],
    "description": "# Feature Specification: ...",
    "priority": {"value": 0, "name": "No priority"},
    "state": "Backlog"
  },
  "speckit:plan": { ... },
  ...
}
```

## Status

The initial snapshot will be captured during T019 implementation. Until
then, `v051-snapshot.json` is intentionally a placeholder with `__pending__: true`
so the parity test (T046) can be marked `xfail` and converted to a hard
assertion the moment the snapshot lands.
