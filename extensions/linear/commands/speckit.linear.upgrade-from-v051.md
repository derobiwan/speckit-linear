---
description: Detect and archive v0.5.1 legacy artefacts under .specify/legacy-v051/, preserving .specify/config/linear.md.
---

# /speckit.linear.upgrade-from-v051

One-shot migration helper that walks a project last installed with
spec-kit-linear-skills v0.5.1 and moves every legacy agent layout
(`.claude/commands/speckit.*.md`, `.codex/prompts/*`, `.gemini/commands/*`,
`.opencode/command/*`, `.github/agents/*`, `.github/prompts/*`,
`skills/speckit-*/SKILL.md`) into a timestamped archive under
`.specify/legacy-v051/<ISO-ts>/`. The user's
`.specify/config/linear.md` is preserved in place (R6 step 6).

This command is the Linear-extension surface for the upgrade. The
user-facing shell alias `specify upgrade-from-v051` is provided by the
install-global wrapper (T052). Per Constitution P1 (NON-NEGOTIABLE) we
do not patch `src/specify_cli/`; the same flow lands upstream via the
PR tracked in `.specify/upstream.notes`.

## User Input

```text
$ARGUMENTS
```

Supported arguments:

* `--dry-run` — list legacy paths without moving anything (exit 0).
* `--no-prompt` — when multiple agent layouts coexist with no clear
  precedence, exit with code 6 instead of prompting.

## Behavior

The command invokes
`extensions.linear.scripts.upgrade_from_v051.run(project_root, dry_run=...)`
which implements PMO-74 §R6:

1. `detect_legacy_dirs` walks each known glob and returns concrete
   legacy files.
2. `detect_agent` applies the precedence order
   `claude > codex > gemini > opencode > github > skills`.
3. Files are moved into
   `.specify/legacy-v051/<ISO-timestamp>/<original-relative-path>`
   using `git mv` when inside a git repo (blame continuity) and falling
   back to `shutil.move` otherwise.
4. `.specify/config/linear.md` is preserved in place.
5. A `MANIFEST.json` is written into the archive bucket recording
   timestamp, detected agent, speckit version, and the moved paths
   (Data Model §E8).
6. Re-running on an already-upgraded tree is a no-op (`status="no-op"`,
   exit 0) — idempotent per R6.

## Safety invariants

* No Linear MCP calls — the upgrade is purely local (P1, P2, P8).
* No deletions — every legacy artefact is reachable under the archive
  bucket. Restore with
  `git mv .specify/legacy-v051/<ts>/* .`.

## Exit codes (Contract C1)

* `0` — success (including no-op when no legacy layout detected).
* `6` — multiple legacy agent layouts with no clear precedence and
  `--no-prompt` was supplied.

## Tests

* `tests/cli/test_upgrade_from_v051.py` (contract test, T049).
* `tests/cli/fixtures/v051-sample-repo/` (golden fixture).
