# Development

Local development setup for contributors to `speckit-linear`.

## Prerequisites

- Python `>=3.11`
- [`uv`](https://docs.astral.sh/uv/) — fast Python package manager:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- A configured Linear MCP server (only required for integration tests):

  ```bash
  claude mcp add --transport http linear https://mcp.linear.app/mcp
  ```

## Setup

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,linear,test]"
```

This installs the package in editable mode with the three optional groups:

- `linear` — runtime deps for the Linear extension (`tenacity`, `httpx`)
- `dev` — developer tooling (`pytest`, `pytest-asyncio`, `vcrpy`, `ruff`)
- `test` — upstream-compatible test extras (`pytest`, `pytest-cov`)

## Common tasks

```bash
# Run the full test matrix
pytest

# Just the Linear extension tests
pytest extensions/linear/tests/

# Upstream-sync invariant check
pytest tests/upstream-sync/

# 30-agent smoke matrix
pytest tests/smoke/

# Lint
ruff check .
ruff format --check .
```

## Plugin development

- A new **extension** lives at `extensions/<name>/` with an `extension.yml` manifest (see `extensions/git/` as a reference).
- A new **preset** lives at `presets/<name>/` with a `preset.yml` manifest (see `presets/lean/` as a reference).
- The Linear extension and preset are the canonical examples of this fork's customization layer; see `extensions/linear/README.md`.

See `CONTRIBUTING.md` for the full plugin-development guide and upstream-sync procedure.

## Constitution

This repository's governance is captured in Linear issue **PMO-70** (project `speckit-constitution`). Every PR is reviewed against the 9 principles. The two NON-NEGOTIABLE rules to internalise before contributing:

1. **No local patches to `src/specify_cli/`**. Contribute changes upstream to `github/spec-kit` instead. CI gate enforces.
2. **Linear-first storage when the Linear preset is active**. No local-file fallback on MCP unreachability.
