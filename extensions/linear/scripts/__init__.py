"""Linear extension Python package.

Modules:
- :mod:`protocols` — typing.Protocol interfaces for the extension's components
  (declared before the implementations land; see Analyze finding A5)
- :mod:`redacting_filter` — secret-scrubbing logging filter
- :mod:`jsonl_logger` — structured JSON-Lines rotating-file logger
- :mod:`linear_mcp_client` — retry/scrub/log wrapper around the MCP transport
- :mod:`failure_injection` — pytest fixture for transient-failure simulation (T073)
- :mod:`hook_helpers` — shared utilities used by every before/after hook
"""
