"""Typing Protocols for the Linear extension's pluggable components.

Per Constitution P4 (Test-First, NON-NEGOTIABLE), tests are written before
implementation. To let those tests compile and run as part of the test-first
RED step, this module declares the interfaces that the eventual implementations
in `redacting_filter.py`, `jsonl_logger.py`, and `linear_mcp_client.py` must
satisfy. Tests import these Protocols and use them as type stubs.

Addresses Analyze finding A5 (see Linear comment on PMO-71).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Redacting(Protocol):
    """Substitutes secret-shaped substrings with deterministic placeholders.

    Implementations MUST match against (at minimum):
      - OAuth bearer tokens
      - GitHub personal access tokens (``ghp_*``, ``ghs_*``, ``github_pat_*``)
      - Linear workspace UUIDs
      - RFC 5322 email addresses

    Replacements MUST be deterministic — the same input substring always
    produces the same placeholder token of the form ``<TOKEN_xxxxxx>``,
    where ``xxxxxx`` is the first 6 hex chars of the SHA-256 of the input.
    """

    def redact(self, text: str) -> str:
        """Return ``text`` with secret substrings replaced."""
        ...


@runtime_checkable
class RedactingLogFilter(Protocol):
    """Logging filter that runs ``Redacting.redact`` on every record.

    MUST mutate ``record.msg`` and any string args in ``record.args``
    before they reach a handler. MUST always return ``True`` so records
    are not dropped.
    """

    def filter(self, record: logging.LogRecord) -> bool: ...


@runtime_checkable
class JsonLinesLogger(Protocol):
    """Structured logger that writes one JSON object per line.

    Required keys on every record: ``ts`` (ISO 8601 UTC, ms precision),
    ``lvl``, ``cmd``, ``phase``, ``msg``. Optional: ``tool``, ``attempt``,
    ``http``, ``dur_ms``, ``req_id``, ``preview``. The file MUST be rotated
    at 10 MB with the most recent 5 backups retained.
    """

    def log_mcp_attempt(
        self,
        *,
        cmd: str,
        tool: str,
        attempt: int,
        http_status: int | None,
        duration_ms: int,
        request_id: str | None,
        message: str,
        preview: str | None = None,
        level: str = "INFO",
    ) -> None: ...


class LinearMcpExhaustedError(RuntimeError):
    """Raised when bounded retries are exhausted against the Linear MCP server.

    The originating exception is preserved via Python's ``__cause__``
    mechanism (``raise LinearMcpExhaustedError(...) from last_exc``).
    """


@runtime_checkable
class LinearMcpClient(Protocol):
    """Thin wrapper around the Linear MCP transport with bounded retries,
    scrubbed structured logging, and an idempotent call surface.

    Implementations MUST:
      - Retry exactly 3 times on 5xx / 429 / network timeouts with
        exponential backoff (1s, 2s, 4s) and ±25% jitter.
      - NOT retry on 4xx responses; surface them immediately.
      - Raise :class:`LinearMcpExhaustedError` after retry exhaustion,
        preserving the last underlying exception as ``__cause__``.
      - Emit one structured log entry per attempt via the injected
        :class:`JsonLinesLogger`.
      - Scrub request and response payloads through the injected
        :class:`Redacting` filter before any log write.
    """

    def call(self, tool_name: str, /, **arguments: Any) -> dict[str, Any]: ...
