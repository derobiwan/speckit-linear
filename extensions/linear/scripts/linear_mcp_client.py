"""Bounded-retry, scrubbed-logging wrapper around the Linear MCP transport (T013).

Implements the :class:`LinearMcpClient` Protocol from :mod:`protocols`. Uses
:mod:`tenacity` for retry orchestration so the policy is declarative,
introspectable, and testable.

Retry policy (Spec FR-032):
- 3 attempts total
- exponential backoff: 1s, 2s, 4s with ±25% jitter
- transient classes: HTTP 5xx, HTTP 429, ``httpx.ConnectError``, ``httpx.ReadTimeout``
- 4xx responses surface immediately (no retry)
- on exhaustion: :class:`LinearMcpExhaustedError` with ``__cause__``
  pointing at the last underlying exception

Logging (Spec FR-034 + Contract C5):
- one structured log entry per attempt (via :class:`JsonLinesLogger`)
- request/response payloads scrubbed via the injected :class:`Redacting`
- on success: ``INFO`` level
- on transient failure that will retry: ``WARN``
- on retry exhaustion: ``ERROR``

NO local-file fallback on any failure (Spec FR-007, Constitution P2 NON-NEGOTIABLE).
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from extensions.linear.scripts.protocols import (
    JsonLinesLogger,
    LinearMcpExhaustedError,
    Redacting,
)

__all__ = ["LinearMcpClientImpl"]


@dataclass(slots=True)
class _AttemptResult:
    """Internal record passed to the logger after each attempt."""

    attempt: int
    http_status: int | None
    duration_ms: int
    request_id: str | None
    outcome: str  # "success", "retried", "exhausted"
    error_class: str | None
    preview: str | None


class LinearMcpClientImpl:
    """Concrete bounded-retry MCP client."""

    def __init__(
        self,
        *,
        base_url: str,
        transport: httpx.MockTransport | httpx.BaseTransport | None = None,
        logger: JsonLinesLogger,
        redactor: Redacting,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 1.0,
        jitter_percent: float = 0.25,
        transient_http_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
        request_timeout_seconds: float = 30.0,
    ) -> None:
        # Constitution P8 — only HTTPS allowed for outbound.
        if not base_url.startswith("https://"):
            raise ValueError(
                f"Linear MCP base_url must use https:// scheme (got {base_url!r})"
            )
        self._base_url = base_url.rstrip("/")
        self._logger = logger
        self._redactor = redactor
        self._max_attempts = max_attempts
        self._initial_backoff = initial_backoff_seconds
        self._jitter = jitter_percent
        self._transient_statuses = set(transient_http_statuses)
        client_kwargs: dict[str, Any] = {"timeout": request_timeout_seconds}
        if transport is not None:
            client_kwargs["transport"] = transport
        self._http = httpx.Client(**client_kwargs)

    # ----------------------------------------------------------- public API

    def call(self, tool_name: str, /, **arguments: Any) -> dict[str, Any]:
        """Invoke an ``mcp__linear__*`` tool with bounded retries.

        Returns the deserialized JSON body on success. Raises:
        - ``httpx.HTTPStatusError`` for any 4xx (not retried).
        - :class:`LinearMcpExhaustedError` after all 3 attempts fail (with
          ``__cause__`` set to the final underlying exception).
        """
        last_exc: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            start = time.monotonic()
            try:
                response = self._send(tool_name, arguments)
                duration_ms = int((time.monotonic() - start) * 1000)
                request_id = response.headers.get("x-request-id")

                if response.status_code in self._transient_statuses:
                    # Transient — log WARN and either retry or fall through to exhaust.
                    self._log_attempt(
                        tool_name,
                        _AttemptResult(
                            attempt=attempt,
                            http_status=response.status_code,
                            duration_ms=duration_ms,
                            request_id=request_id,
                            outcome="retried"
                            if attempt < self._max_attempts
                            else "exhausted",
                            error_class=None,
                            preview=self._preview(arguments),
                        ),
                        level="WARN",
                        message=f"transient HTTP {response.status_code}; "
                        f"{'will retry' if attempt < self._max_attempts else 'exhausted'}",
                    )
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    if attempt < self._max_attempts:
                        self._sleep_with_backoff(attempt)
                        continue
                    raise LinearMcpExhaustedError(
                        f"Linear MCP retries exhausted for {tool_name} "
                        f"(last status: {response.status_code}, req_id: {request_id})"
                    ) from last_exc

                # 4xx — surface immediately, do not retry.
                if 400 <= response.status_code < 500:
                    self._log_attempt(
                        tool_name,
                        _AttemptResult(
                            attempt=attempt,
                            http_status=response.status_code,
                            duration_ms=duration_ms,
                            request_id=request_id,
                            outcome="failed",
                            error_class="HTTPStatusError",
                            preview=self._preview(arguments),
                        ),
                        level="ERROR",
                        message=f"client error HTTP {response.status_code}; surfacing (no retry)",
                    )
                    response.raise_for_status()

                # Success path.
                response.raise_for_status()
                self._log_attempt(
                    tool_name,
                    _AttemptResult(
                        attempt=attempt,
                        http_status=response.status_code,
                        duration_ms=duration_ms,
                        request_id=request_id,
                        outcome="success",
                        error_class=None,
                        preview=self._preview(arguments),
                    ),
                    level="INFO",
                    message="succeeded",
                )
                return response.json() if response.content else {}

            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ) as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                last_exc = exc
                self._log_attempt(
                    tool_name,
                    _AttemptResult(
                        attempt=attempt,
                        http_status=None,
                        duration_ms=duration_ms,
                        request_id=None,
                        outcome="retried"
                        if attempt < self._max_attempts
                        else "exhausted",
                        error_class=type(exc).__name__,
                        preview=self._preview(arguments),
                    ),
                    level="WARN",
                    message=f"transient network error ({type(exc).__name__}); "
                    f"{'will retry' if attempt < self._max_attempts else 'exhausted'}",
                )
                if attempt < self._max_attempts:
                    self._sleep_with_backoff(attempt)
                    continue
                raise LinearMcpExhaustedError(
                    f"Linear MCP retries exhausted for {tool_name} (network)"
                ) from last_exc

        # Defensive — loop body always returns or raises.
        raise LinearMcpExhaustedError(
            f"Linear MCP retries exhausted for {tool_name} (unexpected fall-through)"
        ) from last_exc

    def close(self) -> None:
        self._http.close()

    # --------------------------------------------------------- internals

    def _send(self, tool_name: str, arguments: dict[str, Any]) -> httpx.Response:
        payload = {"tool": tool_name, "arguments": arguments}
        return self._http.post(self._base_url, json=payload)

    def _sleep_with_backoff(self, attempt: int) -> None:
        # 1s, 2s, 4s — exponential.
        base = self._initial_backoff * (2 ** (attempt - 1))
        jitter = base * self._jitter
        delay = base + random.uniform(-jitter, jitter)
        if delay > 0:
            time.sleep(delay)

    def _preview(self, arguments: dict[str, Any]) -> str:
        try:
            raw = json.dumps(arguments, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError):
            raw = repr(arguments)
        return self._redactor.redact(raw)[:200]

    def _log_attempt(
        self,
        tool_name: str,
        result: _AttemptResult,
        *,
        level: str,
        message: str,
    ) -> None:
        self._logger.log_mcp_attempt(
            cmd="<wrapper>",  # the calling hook overrides via contextvar in production
            tool=tool_name,
            attempt=result.attempt,
            http_status=result.http_status,
            duration_ms=result.duration_ms,
            request_id=result.request_id,
            message=message,
            preview=result.preview,
            level=level,
        )
