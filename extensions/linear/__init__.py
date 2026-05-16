"""The Linear extension for speckit-linear.

Provides:
- Linear MCP-backed storage for spec-kit artifacts
- Bounded-retry, scrubbed-logging MCP client
- `before_*` / `after_*` hooks for each of the 9 core spec-kit commands
- Namespaced commands: `speckit.linear.baseline`, `speckit.linear.migrate`,
  `speckit.linear.repair`, `speckit.linear.upgrade-from-v051`

This package is loaded by upstream's `ExtensionManager`; entry point shape
is declared in `extensions/linear/extension.yml`.
"""
