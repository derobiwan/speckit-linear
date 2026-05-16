# Version

| Component | Version | Notes |
|-----------|---------|-------|
| `speckit-linear` (this repo) | `1.0.0` | Released 2026-05-16. See `CHANGELOG.md` for the rebuild scope. |
| Upstream tracker — `github/spec-kit` | `v0.8.10` | Pinned at commit `0e5b59fcaa1deb976c1f73b47c743de1cf5a5d71` (see `.specify/upstream.pin`) |
| Python | `>=3.11` | Matches upstream `requires-python` |

## Sync policy

Per Constitution Principle 1 (Upstream Compatibility, NON-NEGOTIABLE):

- `src/specify_cli/`, `templates/`, `integrations/`, `extensions/{git,selftest,template}/`, `presets/{lean,scaffold,self-test}/`, and `scripts/{bash,powershell}/` are vendored from upstream verbatim and MUST NOT be modified locally.
- All Linear-specific functionality lives in `extensions/linear/` and `presets/linear/`.
- The CI gate `tests/upstream-sync/test_src_specify_cli_unmodified.py` (T055) enforces byte-identity at every PR.

To bump the upstream tracker:

```bash
./scripts/maintainer/sync-upstream.sh v0.8.11
```

See `CONTRIBUTING.md` § "Syncing with upstream" for the procedure.
