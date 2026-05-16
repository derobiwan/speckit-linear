# Agent Runtime Contract

How an AI agent interacts with this repo at runtime. **Audience**: agent developers (the humans driving Claude Code / Codex / Gemini / Copilot / OpenCode / Cursor / Windsurf / etc.) plus the agents themselves reading this file as context.

`CLAUDE.md` is a symlink to this file. Edit `AGENTS.md` only.

## What this repo provides

A plugin layer on top of upstream `github/spec-kit v0.8.10` that persists Spec-Driven Development artifacts to **Linear** instead of the local filesystem.

- 11 user-facing `/speckit.*` slash commands (same names as the v0.5.1 fork; identical to upstream's set).
- A Linear extension at `extensions/linear/` that owns the Linear MCP boundary.
- A Linear preset at `presets/linear/` that wraps the upstream command templates so each one persists artifacts to Linear.

The agent never sees `extensions/linear/` or `presets/linear/` directly — those are loaded by `specify init` once at install time and then drive the runtime via hooks.

## The 11 user-facing commands

Invoke from your AI agent's chat / command surface (`/` in Claude Code, etc.). Each command persists to Linear via the active preset.

| Command | Purpose | Linear output |
|---------|---------|---------------|
| `/speckit.constitution` | Define / amend project principles | One `[CONSTITUTION]` issue in the `speckit-constitution` project |
| `/speckit.specify <feature description>` | Capture feature requirements | `[SPEC] NNN: Name` + initial `[CHECKLIST]` issue |
| `/speckit.clarify` | Resolve up-to-5 ambiguities in the active spec | In-place update to the `[SPEC]` issue body |
| `/speckit.plan` | Produce the technical strategy | 5 issues: `[PLAN]`, `[RESEARCH]`, `[DATA-MODEL]`, `[QUICKSTART]`, `[CONTRACT]` (all sharing the feature label) |
| `/speckit.tasks` | Break the plan into ordered work items | Phase milestones + one issue per task |
| `/speckit.analyze` | Cross-artifact consistency report | Comment on the `[SPEC]` issue (read-only otherwise) |
| `/speckit.checklist` | Generate a quality-validation checklist | New `[CHECKLIST]` issue (multiple per feature OK) |
| `/speckit.implement` | Execute tasks; mark them Done as you go | Status updates on task issues |
| `/speckit.baseline` | Generate a spec by analyzing existing code | `[SPEC]` issue (routes through `/speckit.linear.baseline` per FR-010) |
| `/speckit.migrate` | Relabel a legacy backlog into the dual-label convention | Bulk relabel (routes through `/speckit.linear.migrate`) |
| `/speckit.taskstoissues` | Deprecated under the Linear preset (tasks are already issues) | Informational no-op |

### Namespaced maintenance commands (Linear extension)

These are exposed only when the Linear extension is installed.

| Command | Purpose |
|---------|---------|
| `/speckit.linear.repair` | Recreate missing canonical labels; surface drift |
| `/speckit.linear.baseline` | Underlying implementation of `/speckit.baseline` |
| `/speckit.linear.migrate` | Underlying implementation of `/speckit.migrate` |
| `/speckit.linear.upgrade-from-v051` | Archive legacy v0.5.1 layouts |

## Invoking `specify init` correctly

A fresh project needs:

```bash
specify init --ai <agent-name> --preset linear --extension linear
```

- **`--ai`**: one of 30 supported agents. Examples: `claude`, `codex`, `gemini`, `copilot`, `opencode`, `cursor-agent`, `windsurf`, `goose`, …
- **`--preset linear`**: enables the Linear preset (wraps the 11 core command templates).
- **`--extension linear`**: enables the Linear extension (loads the hooks + MCP client).

Both `--preset` and `--extension` are **required together** — the preset depends on the extension and `specify init` refuses to install one without the other (FR-004).

If the Linear MCP server is not configured, install fails fast with the exact `claude mcp add ...` command in the error message (FR-002).

The `install-global/install.sh` wrapper sets both flags by default so users who installed via curl don't have to remember them.

## What the agent sees at runtime

When the user invokes a `/speckit.*` command:

1. The preset wrapper around the upstream template fires.
2. **Before-hook** runs first (e.g., resolve active feature, ensure product project exists, allocate feature label).
3. The CLI emits one stderr line confirming the backend:

   ```text
   [linear] backend=Linear workspace=<team-name> project=<product-project-name>
   ```

4. The command body (from the upstream template + preset wrap) runs.
5. **After-hook** persists the artifact via `mcp__linear__save_issue` (or `save_milestone`, `save_comment`, …).
6. Retries on transient failures (3 attempts, 1s/2s/4s ±25% jitter on 5xx/429/timeout). 4xx surfaces immediately.
7. Every MCP attempt → `.specify/logs/linear-mcp.log` (JSON Lines, scrubbed, rotated at 10 MB).

## Required tooling

The agent's host environment must provide:

| Requirement | Why |
|-------------|-----|
| Linear MCP server reachable via `claude mcp` | All artifact storage flows through it (no local fallback — Constitution P2) |
| Python `>=3.11` | Matches upstream `requires-python` |
| `uv` | Used by `install-global/install.sh` and by the maintainer's CI matrix |
| Git | The "Find Active Feature" pattern falls back to the current branch name (`NNN-…`) when `.specify/config/linear.md` doesn't pin a feature |

## Find Active Feature pattern

Most commands need to know which feature you're working on. Resolution order:

1. **Explicit argument** — `/speckit.plan 003-payment-flow`
2. **`feature:NNN-short-name` line** in `.specify/config/linear.md`
3. **Current git branch** if it matches `NNN-short-name`
4. **Ask the user** — list existing `feature:*` labels via Linear MCP

## Spec Kit workflow (canonical sequence — MANDATORY)

The lifecycle MUST be executed in this order. Steps are not skippable. Optional skills (clarify, checklist, analyze) may be omitted, but the remaining steps still execute in this order. Each user-scoped skill (`~/.claude/skills/speckit-*/SKILL.md`) and each Linear preset command (`presets/linear/commands/speckit.*.md`) carries its own **Workflow Position** block that enforces this gate at invocation time.

```text
1. Constitution            →  speckit.constitution           (one-time per repo)
2. Specify                 →  speckit.specify                (or speckit.baseline for brownfield)
3. Clarify (optional)      →  speckit.clarify                — BEFORE plan
4. Plan                    →  speckit.plan                   (produces 5 artifacts)
5. Checklist (optional)    →  speckit.checklist              — AFTER plan, BEFORE tasks (may repeat)
6. Tasks                   →  speckit.tasks                  (produces milestones + tasks)
7. Analyze (optional)      →  speckit.analyze                — AFTER tasks, BEFORE implement
8. Implement               →  speckit.implement
```

### Dependencies (hard gates)

- Constitution before first specify / baseline.
- Specify / baseline before clarify, plan, or checklist.
- Plan before checklist (when used as a quality gate) and before tasks.
- Tasks before analyze and before implement.
- Analyze before implement (when invoked).

### Workflow Scenarios

- **Greenfield**: constitution → specify → [clarify] → plan → [checklist] → tasks → [analyze] → implement
- **Brownfield**: constitution → baseline → [clarify] → plan → [checklist] → tasks → [analyze] → implement
- **Legacy docs**: constitution → baseline → clarify → plan → [checklist] → tasks → [analyze] → implement
- **Backlog migration**: constitution → migrate → plan → [checklist] → tasks → [analyze] → implement

### Deviation policy

The sequence is non-negotiable. If a step appears to be missing in the artifact graph, the agent MUST abort, surface the violation, and ask for explicit user confirmation to deviate (deviation requires the user to acknowledge the downstream rework risk in writing). Skipping a required step silently — even at user request — is a contract violation.

## Linear data model

All artifacts have **dual labels**: `speckit:<type>` + `feature:NNN-short-name`.

```text
speckit-constitution (Project)
└── [CONSTITUTION] Project Constitution    speckit:constitution

<Product Project>  (configured in .specify/config/linear.md)
├── [SPEC]      001: Feature Name           speckit:spec       + feature:001-name
├── [PLAN]      001: Implementation Plan    speckit:plan       + feature:001-name
├── [RESEARCH]  001: Technical Research     speckit:research   + feature:001-name
├── [DATA-MODEL] 001: Entity Definitions    speckit:data-model + feature:001-name
├── [QUICKSTART] 001: Integration Guide     speckit:quickstart + feature:001-name
├── [CONTRACT]  001: API Contract           speckit:contract   + feature:001-name
├── [CHECKLIST] 001: <domain> Quality       speckit:checklist  + feature:001-name
├── 001: Phase 1: Setup (Milestone)
│   ├── T001 Task description               speckit:task + feature:001-name
│   └── T002 [P] Task description           speckit:task + feature:001-name + parallelizable
└── ...
```

Full mapping: `.specify/config/linear.md`.

## Idempotency contract

Every artifact-producing command MUST be idempotent on re-invocation. If an issue exists for the same `feature:NNN-name` + `speckit:<type>` pair, the command calls `save_issue` with the **existing id** to update in place. The command MUST NOT create duplicate issues with version suffixes (`v2`, `v3`, …) and MUST NOT delete-then-recreate.

This is FR-031, NON-NEGOTIABLE. The contract tests under `extensions/linear/tests/contract/` pin it for every command.

## Best practices

- Follow the sequence — each phase builds on the previous.
- Keep specs technology-agnostic — framework choices belong in plan.
- Maximum 3 `[NEEDS CLARIFICATION]` markers per spec; use `/speckit.clarify` to resolve.
- Run `/speckit.analyze` before `/speckit.implement` on anything non-trivial.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Linear MCP server not reachable` at install | Run the exact command from the error message: `claude mcp add --transport http linear https://mcp.linear.app/mcp`. Then re-run `specify init`. |
| `No constitution found` | Run `/speckit.constitution` first. |
| `Product project not found` | Set the product project name in `.specify/config/linear.md` (the file the first `/speckit.specify` run updates for you), or pass `--product-project <name>` to your install. |
| `Too many clarification markers` | Make informed guesses with **Assumptions** in the spec, then run `/speckit.clarify` after to firm them up. |
| `Plan violates constitution` | Either revise the plan or document an explicit exception in the constitution. |
| `Linear MCP auth failed` mid-workflow | Re-authenticate the MCP server. The CLI surfaces the error verbatim; there is no local-file fallback (Constitution P2). |
| Drifted labels | Run `/speckit.linear.repair`. |
| Re-run is creating duplicate issues | Bug — `save_issue` should be reusing the existing id. Open an issue and reference FR-031. |

## Contributing

Read [CONTRIBUTING.md](./CONTRIBUTING.md). Patching `src/specify_cli/` is forbidden by Constitution P1 — open the PR against `github/spec-kit` instead.
