# `install-global/` — one-line installer for speckit-linear

Implements **FR-003**: a single shell pipe (curl + bash or PowerShell)
that bootstraps the entire toolchain end-to-end and leaves the user with
a working project pointing at Linear as its storage backend.

## Quick install

### macOS / Linux / WSL

```bash
curl -fsSL https://raw.githubusercontent.com/derobiwan/speckit-linear/main/install-global/install.sh | bash
```

With flags:

```bash
curl -fsSL https://.../install.sh | bash -s -- --ai claude --here
```

### Windows (PowerShell 7+)

```powershell
irm https://raw.githubusercontent.com/derobiwan/speckit-linear/main/install-global/install.ps1 | iex
```

With flags:

```powershell
.\install.ps1 -Ai claude -Here
```

## What the installer does

1. **uv**: installs (or detects) Astral's `uv` package manager.
2. **specify**: `uv tool install --force speckit-linear`. Falls
   back to the GitHub source if the PyPI package is unavailable.
3. **Agent detection**: picks the first agent CLI found on `PATH` using
   the precedence `claude > codex > gemini > copilot > opencode`. If
   none are found, prompts on TTY or defaults to `copilot` (no CLI
   required).
4. **`specify init`**: runs the upstream init with `--integration <agent> --preset linear`.

Once the upstream PR for `--extension linear` lands (see
`.specify/upstream.notes`), the installer will append `--extension linear`
automatically.

## Flags

| Bash flag        | PowerShell parameter | Description |
| -----------------| -------------------- | ----------- |
| `--ai <name>`    | `-Ai <name>`         | Skip auto-detection; use this agent. |
| `--here`         | `-Here`              | Init in the current directory. |
| `--target <dir>` | `-Target <dir>`      | Init into the named directory. |
| `--no-git`       | `-NoGit`             | Don't initialise a git repo. |
| `--no-prompt`    | `-NoPrompt`          | Never prompt; default to `copilot` if no agent CLI is found. |

## Environment variables

| Variable          | Effect |
| ----------------- | ------ |
| `INSTALL_DRY_RUN` | Set to `1` to print each step without executing. |
| `SPECIFY_SOURCE`  | Override the `uv tool install` source (e.g. a local wheel). |

## Post-install

Configure the Linear MCP server (one-time per Claude Code install):

```bash
claude mcp add --transport http linear https://mcp.linear.app/mcp
```

Then run `/speckit.constitution` and `/speckit.specify` in your agent.
