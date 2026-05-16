# Contributing to speckit-linear

## Project boundaries (read first)

This repo lives at the seam of three things. Knowing where your change belongs is the single most important thing to get right before opening a PR.

| Layer | Owner | Path | Rule |
|-------|-------|------|------|
| Upstream `spec-kit` CLI | `github/spec-kit` | `src/specify_cli/`, `templates/commands/`, `integrations/`, `extensions/{git,selftest,template}/`, `presets/{lean,scaffold,self-test}/`, `scripts/{bash,powershell}/` | **No local patches.** Open the PR against upstream and reference it in `.specify/upstream.notes`. Constitution P1, NON-NEGOTIABLE. |
| Linear **extension** | this repo | `extensions/linear/` | New Linear-specific behaviour, MCP wiring, hook scripts, namespaced commands (`speckit.linear.*`) live here. |
| Linear **preset** | this repo | `presets/linear/` | Wraps the 11 core command templates from upstream. Use `strategy: wrap` (Constitution P6) so future upstream template improvements flow through. |

The full vendored set is encoded in [`tests/upstream-sync/test_src_specify_cli_unmodified.py::VENDORED_DIRS`](tests/upstream-sync/test_src_specify_cli_unmodified.py) — that test is the source of truth.

## Filing changes against upstream

If your change touches the CLI itself (a new flag, a parser bug, a missing integration):

1. Reproduce against an unmodified upstream clone.
2. Open the PR against `github/spec-kit` — not this repo.
3. Record the upstream PR link in `.specify/upstream.notes` so the next maintainer can pick it up after it lands.
4. Until the upstream PR merges, work around the gap behind the Linear extension surface (a before-hook, a wrapper script under `install-global/`, or `extensions/linear/scripts/...`). **Never edit `src/specify_cli/` locally** — even a temporary patch breaks the P1 invariant and the upstream-sync CI gate will block the PR.

## Adding a new extension

The Linear extension is the only one this repo ships, but the upstream `ExtensionManifest` accepts any extension that conforms to its schema. To add a new one:

1. Create `extensions/<id>/` with the following minimum layout:

   ```text
   extensions/<id>/
   ├── extension.yml           # schema v1.0 manifest
   ├── README.md               # what it does, one paragraph
   ├── config-template.yml     # copied to .specify/config/<id>.yml at install (optional)
   ├── commands/               # namespaced command markdown files (speckit.<id>.<name>.md)
   ├── hooks/                  # before_*/after_* Python hook scripts
   ├── scripts/                # shared Python (clients, helpers)
   └── tests/                  # contract + integration + unit suites
   ```

2. Author `extension.yml` against the schema in `src/specify_cli/extensions.py` (`ExtensionManifest`). Required fields: `extension.id`, `extension.version`, `extension.name`, `requires.speckit_version`, `provides.commands`, `hooks`. Mark any required MCP tools in `requires.tools` with `required: true` so the CLI fails fast on missing servers.

3. **Write the manifest schema test first** (Constitution P4). Mirror the pattern in [`extensions/linear/tests/contract/test_extension_manifest.py`](extensions/linear/tests/contract/test_extension_manifest.py) — load the manifest through the upstream validator and pin every assumption your hooks rely on.

4. For each hook command in `extension.yml`, author a backing markdown prompt under `commands/` that:
   - has YAML frontmatter
   - mentions the MCP tool prefix the runtime should grant the extension (e.g. `mcp__<server>__`)
   - explicitly signals "no local-file fallback" for resolver hooks (Constitution P2)
   - calls `save_*`/`create_*` for persister hooks (Constitution P2)

   The shared parametrised test [`extensions/linear/tests/contract/test_hook_commands.py`](extensions/linear/tests/contract/test_hook_commands.py) is a copy-paste-able starter.

5. Wire the new extension into `pyproject.toml`'s `[project.optional-dependencies]` if it needs extra runtime deps. Document the install path in `README.md`.

## Adding a new preset

Presets compose templates and command overrides; they cannot create new commands of their own (use an extension for that).

1. Create `presets/<id>/preset.yml` declaring overrides for the upstream commands you want to wrap. Use `strategy: wrap` — `replace` skips upstream improvements and breaks Constitution P6.

2. Each override goes under `presets/<id>/commands/<command>.md`. Keep the file thin — the upstream template is the source of truth; your override only inserts the Linear-flavoured before/after blocks.

3. Declare `requires.extensions: [{id: <extension-id>, version: ">=1.0.0,<2.0.0"}]` if the preset needs an extension installed.

4. **Write the preset-manifest contract test first** ([`extensions/linear/tests/contract/test_preset_manifest.py`](extensions/linear/tests/contract/test_preset_manifest.py) is the template). Cover: every core command has an override, every override uses `strategy: wrap`, every `replaces` field names the matching command.

## Test-first (NON-NEGOTIABLE)

Constitution P4: every implementation task ships **after** its failing test in the same phase commit. The reviewer can verify this with `git log -p` — the test file appears in the commit chain before the impl file.

- Contract tests: `extensions/<id>/tests/contract/` — pin the MCP call shape (tool name, argument keys).
- Integration tests: `extensions/<id>/tests/integration/` — exercise the whole flow against an in-memory MCP fake or a VCR cassette.
- Unit tests: `extensions/<id>/tests/unit/` — for helpers (`hook_helpers.py`, redacting filter, JSONL logger).
- Governance tests: `tests/governance/` — for repo-wide invariants (P1, P9, no-per-agent-shims).

Use `.venv/bin/python -m pytest <path>` to run a slice; pre-commit will run the full suite minus the 30-agent matrix.

## Pre-commit

Install once after `uv pip install -e ".[dev,linear]"`:

```bash
pre-commit install
```

Active hooks:

- `gitleaks` — secret scan (Constitution P8).
- `trailing-whitespace`, `end-of-file-fixer`, `check-{yaml,toml}` — standard hygiene, with `_vendored_exclude` to skip upstream-owned files.
- `ruff`, `ruff-format` — Python lint + format.
- `markdownlint-cli2` — markdown lint.
- `docs-update-gate` (T072) — code-affecting changes must touch one of `README.md|AGENTS.md|CLAUDE.md|CHANGELOG.md|CONTRIBUTING.md|VERSION.md` in the same commit. Escape hatch: `[skip-docs]` in the commit message (audited).

If you add a new mutating hook, mirror the `_vendored_exclude` anchor or the upstream-sync CI gate will flag drift on the next PR.

## Syncing with upstream

This fork vendors `github/spec-kit` and adds the Linear plugin pair on top. **All changes to upstream-vendored files must come through an upstream PR — never a local patch.** The upstream-sync CI gate at [`.github/workflows/upstream-sync.yml`](.github/workflows/upstream-sync.yml) enforces this on every PR.

### Which paths are vendored

Any change here must come from upstream:

- `src/specify_cli/**` — the CLI itself
- `templates/commands/**`
- `integrations/**`
- `extensions/git/**`, `extensions/selftest/**`, `extensions/template/**`
- `presets/lean/**`, `presets/scaffold/**`, `presets/self-test/**`
- `scripts/bash/**`, `scripts/powershell/**`

Fork-only contributions (free to edit) live under:

- `extensions/linear/**`
- `presets/linear/**`
- `tests/**`, `install-global/**`, `scripts/maintainer/**`

### Maintainer procedure: refreshing the upstream vendor

Run this when upstream cuts a new tag we want to track:

```bash
# 1. Fetch the new upstream tag locally.
git fetch https://github.com/github/spec-kit.git --tags

# 2. Run the helper. It rsyncs the vendored dirs from the upstream tag
#    into this repo (deleting files removed upstream), updates
#    .specify/upstream.pin, and prints the resolved commit SHA.
./scripts/maintainer/sync-upstream.sh v0.9.0   # or whatever new tag

# 3. Run the full test suite.
uv pip install -e ".[dev,linear]"
pytest

# 4. Inspect the diff in the Linear-specific dirs. If upstream renamed
#    or removed something a Linear preset/extension depends on, update
#    the Linear side accordingly. Never patch the vendored side.

# 5. Bump the fork's version in VERSION.md and pyproject.toml as needed.

# 6. Commit and open a PR. The upstream-sync CI gate validates the
#    diff against the new pin. CI should be green before merge.
```

## Rollback procedure for `upgrade-from-v051`

`specify upgrade-from-v051` moves legacy directories under `.specify/legacy-v051/<ISO-timestamp>/` and writes a `MANIFEST.json` describing what moved. To roll the upgrade back:

1. Locate the archive: `ls .specify/legacy-v051/` — pick the most recent timestamp.
2. Inspect the manifest: `cat .specify/legacy-v051/<ts>/MANIFEST.json` — every archived path is listed under `archived`.
3. Restore via `git mv` (preferred — preserves blame continuity):

   ```bash
   cd .specify/legacy-v051/<ts>
   while read -r rel; do
     git mv -k "$rel" "$(git rev-parse --show-toplevel)/$rel"
   done < <(jq -r '.archived[]' MANIFEST.json)
   ```

   If you used `--dry-run` originally, the archive was never written and there is nothing to roll back.

4. Remove the empty archive shell: `git rm -r .specify/legacy-v051/<ts>` (only after step 3 completes).

5. Re-run `specify init --ai <agent> --preset linear --extension linear` to recreate the v1.0.0 install state. The two layouts can coexist briefly while you reconcile; `tests/governance/test_no_per_agent_shims.py` will block a commit that re-introduces legacy shims inside the Linear plugin directories.

If the rollback fails (e.g., `git mv` reports a conflict), the original archive remains intact — nothing was deleted. Resolve the conflict and re-run the loop.

## Commit Guidelines

- Short, imperative, sentence-case commit messages.
- Branch names: `feature/short-description`, `bugfix/short-description`, or the `tgrunow/pmo-<n>-<slug>` form Linear's branch-name helper produces.
- PRs: clear summary; reference Linear issue ids (PMO-NN) inline.
- Pre-commit gates must be green before merge — never bypass with `--no-verify`.

## Key Principles

- **Linear is the sole artifact store** — no local `specs/` directory; failures surface, they don't fall back.
- **Dual-label system** — every artifact issue carries both a `speckit:*` and a `feature:NNN-name` label.
- **Single source of truth at every layer** — upstream owns the CLI; this repo owns the Linear plugins; never patch across the boundary.
- **Test-first (P4)** — feature commits are paired (test → impl), reviewable as such.
- **Docs-update (P9)** — code changes ship with a doc update in the same commit, audited via the pre-commit gate.
