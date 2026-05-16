# speckit-linear

Linear-as-storage-backend for [github/spec-kit](https://github.com/github/spec-kit). Spec-Driven Development workflow with **Linear issues as the artifact store** — no local `specs/` directory, no per-agent shim files, full support for all 30 upstream agent integrations.

- **Repo version**: `1.0.0`
- **Upstream tracker**: `github/spec-kit` `v0.8.10` (pinned via `.specify/upstream.pin`)
- **Constitution**: [PMO-70](https://linear.app/pmo-to-do-list/issue/PMO-70) (NON-NEGOTIABLE invariants P1-P9)

## What this is

A fork of upstream `spec-kit` that uses Linear instead of the local filesystem as the spec/plan/tasks store. The fork ships **two plugins** on top of an unmodified upstream:

| Plugin type | What it ships | Path |
|-------------|---------------|------|
| **Integration** | (none — we consume upstream's 30 agent integrations unchanged) | `integrations/` (vendored) |
| **Extension** | The Linear MCP boundary: hooks, scripts, namespaced commands (`/speckit.linear.*`) | `extensions/linear/` |
| **Preset** | Wraps the 11 core `/speckit.*` command templates so each one persists artifacts to Linear instead of disk | `presets/linear/` |

The upstream CLI (`src/specify_cli/`) is **byte-identical** to the pinned tag. A CI gate (`.github/workflows/upstream-sync.yml`) enforces this on every PR.

## Quickstart

Five minutes from zero to your first Linear-backed `[SPEC]` issue.

1. **Install `uv`** if you don't have it.

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2. **Configure the Linear MCP server** (required — there is no local fallback).

    ```bash
    claude mcp add --transport http linear https://mcp.linear.app/mcp
    ```

3. **Install via the one-line wrapper** (auto-detects your AI agent: Claude Code, Codex CLI, Gemini CLI, GitHub Copilot CLI, or OpenCode):

    ```bash
    curl -LsSf https://raw.githubusercontent.com/derobiwan/speckit-linear/main/install-global/install.sh | bash
    ```

    Or, if you prefer to pick the agent yourself:

    ```bash
    uv tool install git+https://github.com/derobiwan/speckit-linear
    cd /path/to/your/project
    specify init --ai claude --preset linear --extension linear
    ```

4. **Create your first feature** — your agent (e.g., Claude Code) now exposes the 11 `/speckit.*` slash commands. Invoke:

    ```text
    /speckit.specify "Add password reset flow"
    ```

    The CLI prints the active backend (`[linear] backend=Linear workspace=… project=…`) and creates a `[SPEC]` issue in Linear with the dual labels `speckit:spec` + `feature:001-…`.

5. **Continue the workflow**:

    ```text
    /speckit.plan       # 5 artifacts → 5 Linear issues
    /speckit.tasks      # phases → milestones, tasks → issues
    /speckit.implement  # marks task issues Done as you go
    ```

> **Already on the v0.5.1 fork?** Run `specify upgrade-from-v051` from your existing project root. Legacy directories (`.claude/`, `.codex/`, `.gemini/`, `.opencode/`, `.github/{agents,prompts}/`, `skills/`) move under `.specify/legacy-v051/<ISO-timestamp>/`. Your Linear workspace is untouched.

## The 11 user-facing commands

| Command | Output | Linear shape |
|---------|--------|--------------|
| `/speckit.constitution` | Project principles | One `[CONSTITUTION]` issue in the `speckit-constitution` project |
| `/speckit.specify` | Feature spec | `[SPEC] NNN: Name` + initial `[CHECKLIST]` |
| `/speckit.clarify` | Spec updates | In-place update of the `[SPEC]` issue |
| `/speckit.plan` | Implementation plan + 4 supporting artifacts | 5 issues: `[PLAN]`, `[RESEARCH]`, `[DATA-MODEL]`, `[QUICKSTART]`, `[CONTRACT]` |
| `/speckit.tasks` | Ordered work items | Phase milestones + one issue per task (`speckit:task` + `feature:NNN-name`) |
| `/speckit.analyze` | Cross-artifact consistency report | Comment on the `[SPEC]` issue |
| `/speckit.checklist` | Quality-validation checklist | New `[CHECKLIST]` issue |
| `/speckit.implement` | Status updates | Transitions task issues to Done |
| `/speckit.baseline` | Spec from existing code | `[SPEC]` issue (routes through preset alias to `/speckit.linear.baseline` per FR-010) |
| `/speckit.migrate` | Relabel legacy backlog | Bulk-relabel of existing issues (alias to `/speckit.linear.migrate`) |
| `/speckit.taskstoissues` | Deprecated — tasks are already issues under the Linear preset | Informational no-op |

The Linear extension also ships namespaced maintenance commands:

| Command | Purpose |
|---------|---------|
| `/speckit.linear.repair` | Recreate missing canonical labels; surface drift in `feature:*` labels |
| `/speckit.linear.upgrade-from-v051` | Archive legacy v0.5.1 directories under `.specify/legacy-v051/` |
| `/speckit.linear.{baseline,migrate}` | Underlying implementations of the FR-010 aliases above |

## Supported AI agents

All 30 upstream-supported integrations:

```text
agy, auggie, bob, claude, codebuddy, codex, copilot, cursor-agent,
devin, forge, gemini, goose, iflow, junie, kimi, kiro-cli, lingma,
opencode, pi, qodercli, qwen, roo, shai, tabnine, trae, vibe,
warp, windsurf, zed-cli, zsh
```

Install for any of them: `specify init --ai <name> --preset linear --extension linear`.

The 30-agent install matrix is verified on every PR via [`.github/workflows/agent-matrix.yml`](.github/workflows/agent-matrix.yml).

## Architecture

```text
upstream spec-kit (vendored, byte-identical)
├── src/specify_cli/          ← CLI; we add nothing here (Constitution P1)
├── integrations/             ← 30 agent integrations
├── templates/commands/       ← 11 core command templates
├── extensions/{git,selftest,template}/
├── presets/{lean,scaffold,self-test}/
└── scripts/{bash,powershell}/

fork-only (this repo)
├── extensions/linear/        ← Linear MCP boundary
│   ├── extension.yml         ← Plugin manifest: tools, commands, 18 hooks
│   ├── hooks/                ← before_*/after_* hooks per core command
│   ├── scripts/              ← MCP client, redacting filter, JSONL logger
│   └── commands/             ← Namespaced commands (speckit.linear.*)
├── presets/linear/           ← Wraps the 11 core command templates
│   ├── preset.yml            ← Composition manifest
│   └── commands/             ← Wrap-strategy overrides
├── install-global/           ← One-line install wrapper (bash + PowerShell)
├── scripts/maintainer/       ← Upstream sync helper + docs-update gate
└── tests/                    ← Fork-authored test suite (≤ 5 min budget)
```

The full vendored set is encoded in `tests/upstream-sync/test_src_specify_cli_unmodified.py::VENDORED_DIRS` — that test is the source of truth for what counts as "upstream-owned" and runs on every CI pass.

## Constitution invariants

| # | Rule | Enforced by |
|---|------|-------------|
| **P1** | No patches to `src/specify_cli/` | `tests/upstream-sync/` + CI gate |
| **P2** | Linear-first storage, no local fallback on MCP failure | `LinearMcpClientImpl` raises `LinearMcpExhaustedError`; no fixture writes locally |
| **P4** | Test-First (NON-NEGOTIABLE) | Test commits precede impl commits in every TDD pair |
| **P6** | Preset overrides use `strategy: wrap`, never `replace` | `tests/contract/test_preset_manifest.py` |
| **P8** | Linear MCP server is the only credential boundary | `RedactingFilter` scrubs every payload before logging; gitleaks pre-commit |
| **P9** | Code changes ship with a doc update | `scripts/maintainer/docs_update_gate.py` (pre-commit hook) |

Read the full constitution in Linear: [PMO-70 — Constitution](https://linear.app/pmo-to-do-list/issue/PMO-70).

## How storage works (short version)

Every command goes through the same pipeline:

```text
agent runtime  →  /speckit.<cmd>  →  preset wrapper  →  before-hook
                                                          ↓
                                                     Linear MCP
                                                          ↓
                                       artifact → save_issue / save_milestone
                                                          ↓
                                                      after-hook
                                                          ↓
                                              backend confirmation line
```

- Active feature resolution: `.specify/config/linear.md` → git branch (`NNN-name`) → ask user.
- Idempotency: every artifact-producing command calls `save_issue` with the existing id when a matching `feature:NNN-name + speckit:<type>` pair already exists.
- Retries: 3 attempts with 1s/2s/4s ±25% jitter on 5xx/429/network timeouts; 4xx surfaces immediately. Configured via `linear-config.yml` (extension defaults).
- Logging: every MCP attempt → `.specify/logs/linear-mcp.log` (JSON Lines, rotated at 10 MB, secrets scrubbed before write).

Full data-model mapping: `.specify/config/linear.md`.

## Upgrading from v0.5.1

```bash
cd /path/to/your/v051/project
specify upgrade-from-v051
```

Legacy directories move under `.specify/legacy-v051/<ISO-timestamp>/`. A `MANIFEST.json` records what moved. Re-running is idempotent. Your Linear data is untouched.

See `CONTRIBUTING.md` § "Rollback procedure for upgrade-from-v051" if you need to revert.

## Contributing

- **Patching `src/specify_cli/`** is forbidden by Constitution P1. Open a PR against `github/spec-kit` and reference it in `.specify/upstream.notes`.
- **New Linear-only behaviour** belongs under `extensions/linear/` or `presets/linear/`.
- **Pre-commit** runs gitleaks, ruff, markdownlint, the upstream-sync exclude regex, and the P9 docs-update gate. Install with `pre-commit install` after `uv pip install -e ".[dev,linear]"`.

Full contributor guide: [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

[AGPL-3.0](./LICENSE).
