# Changelog

All notable changes to this project will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-16

First public release of `speckit-linear` — Linear extension + preset for [GitHub Spec Kit](https://github.com/github/spec-kit).

Persists all Spec-Driven Development artifacts (constitution, spec, plan, tasks, research, contracts, checklists) as Linear issues via the official Linear MCP server. Replaces local-file storage; designed to be installed as the pair `--extension linear --preset linear` through the Spec Kit community catalog.

### Highlights

- **Plugin model**: ships as `extensions/linear/` extension + `presets/linear/` preset on top of unmodified upstream `github/spec-kit` v0.8.10. The 11 user-facing `/speckit.*` slash commands are reimplemented via preset wrapping.
- **30 supported AI agent integrations** — all install through `specify init --ai <agent> --extension linear --preset linear`.
- **Canonical Spec Kit lifecycle enforced at the skill surface** (`constitution → specify → [clarify] → plan → [checklist] → tasks → [analyze] → implement`). Every preset command body carries a `Workflow Position (MANDATORY)` block that aborts if a required predecessor artifact is missing.
- **Bounded retry** on every Linear MCP call (3 attempts, 1s/2s/4s ±25% jitter on 5xx/429/timeout; 4xx surfaces immediately).
- **Structured JSON Lines logging** of every MCP attempt to `.specify/logs/linear-mcp.log` with secrets scrubbed.
- **Backend confirmation banner**: `[linear] backend=Linear workspace=<name> project=<name>` printed once per process on stderr.
- **Idempotent every artifact-producing command** (FR-031, non-negotiable): re-running `/speckit.specify`, `/speckit.plan`, etc. updates in place rather than creating duplicates.
- **Dual-label convention** in Linear: every issue carries one `speckit:<type>` label plus a `feature:NNN-name` label so all issues for one feature can be filtered together.
- **Single shared product project** for all features (`.specify/config/linear.md`), distinct from the singleton `speckit-constitution` project.

### Prerequisites

- Linear MCP server reachable via `claude mcp`: `claude mcp add -s user --transport http linear https://mcp.linear.app/mcp`
- Python `>=3.11`, `uv`, `git`
- Install: `specify init --ai <agent> --extension linear --preset linear`

### License

MIT. See `LICENSE`.
