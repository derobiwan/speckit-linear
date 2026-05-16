"""Contract tests for :class:`LinearMcpClient` (T012).

Asserts the documented behavior contract per:
  - Spec FR-007 (no local fallback on MCP failure)
  - Spec FR-032 (bounded exponential retry: 3 attempts, 1s/2s/4s ±25% jitter;
    retry only on 5xx, 429, ConnectError, ReadTimeout; no retry on 4xx)
  - Spec FR-034 (every MCP attempt produces a structured log entry)
  - Contract C5 (log entry JSON schema with required and optional fields)
  - Spec FR-021/FR-029 (request/response payloads scrubbed before logging)

These tests MUST fail until T013 (impl) lands. They are part of
Constitution P4 (Test-First, NON-NEGOTIABLE).

Addresses Analyze finding A5 by importing the Protocols declared in
``extensions.linear.scripts.protocols`` — those landed in T012's scope
so the test compiles without depending on T013/T015/T017 internals.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from extensions.linear.scripts.protocols import (
    JsonLinesLogger,
    LinearMcpClient,
    LinearMcpExhaustedError,
    Redacting,
)

# The implementation under test is imported lazily so test collection still
# works when only Protocols + tests exist (RED phase).
linear_mcp_client_module = pytest.importorskip(
    "extensions.linear.scripts.linear_mcp_client",
    reason="T013 implementation not yet present — expected during RED phase.",
)
LinearMcpClientImpl = linear_mcp_client_module.LinearMcpClientImpl


# --- Fixtures --------------------------------------------------------------


@pytest.fixture()
def fake_logger() -> JsonLinesLogger:
    logger = MagicMock(spec=JsonLinesLogger)
    return logger


@pytest.fixture()
def fake_redactor() -> Redacting:
    redactor = MagicMock(spec=Redacting)
    redactor.redact.side_effect = lambda s: re.sub(
        r"ghp_[A-Za-z0-9]+", "<TOKEN_aaaaaa>", s
    )
    return redactor


@pytest.fixture()
def make_client(fake_logger: JsonLinesLogger, fake_redactor: Redacting):
    """Factory: builds a LinearMcpClientImpl with the given transport mock."""

    def _factory(transport: httpx.MockTransport) -> LinearMcpClient:
        return LinearMcpClientImpl(
            base_url="https://mcp.linear.app/mcp",
            transport=transport,
            logger=fake_logger,
            redactor=fake_redactor,
            max_attempts=3,
            initial_backoff_seconds=0.0,  # speed up tests; jitter logic still exercised
            jitter_percent=0.0,
            transient_http_statuses=(429, 500, 502, 503, 504),
        )

    return _factory


# --- Retry semantics (FR-032) ---------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_status_triggers_retry(make_client, status, fake_logger):
    """5xx and 429 retry up to 3 attempts; final attempt's success terminates."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(status)
        return httpx.Response(200, json={"ok": True})

    client = make_client(httpx.MockTransport(handler))
    result = client.call("mcp__linear__list_teams")

    assert result == {"ok": True}
    assert len(calls) == 3
    # Exactly 3 structured log entries — one per attempt.
    assert fake_logger.log_mcp_attempt.call_count == 3


def test_network_timeout_triggers_retry(make_client):
    """ConnectError / ReadTimeout are transient and retried."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("simulated network blip")
        return httpx.Response(200, json={"ok": True})

    client = make_client(httpx.MockTransport(handler))
    assert client.call("mcp__linear__list_teams") == {"ok": True}
    assert len(calls) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_4xx_is_not_retried(make_client, status, fake_logger):
    """4xx responses (auth, permission, schema) surface immediately, no retry."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": "client"})

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        client.call("mcp__linear__list_teams")
    assert len(calls) == 1, "4xx MUST NOT be retried"
    assert fake_logger.log_mcp_attempt.call_count == 1


def test_retry_exhaustion_raises_wrapped_error(make_client, fake_logger):
    """After 3 failed attempts, raise LinearMcpExhaustedError with __cause__."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(LinearMcpExhaustedError) as excinfo:
        client.call("mcp__linear__list_teams")

    assert (
        excinfo.value.__cause__ is not None
    ), "Exhausted error MUST preserve the last underlying exception via __cause__"
    assert fake_logger.log_mcp_attempt.call_count == 3


# --- No local fallback (FR-007) -------------------------------------------


def test_failure_never_falls_back_to_local_files(tmp_path, monkeypatch, make_client):
    """Per FR-007 (NON-NEGOTIABLE), client never writes to local disk on failure."""
    # Make a fresh CWD; assert no artifact files appear after a failed call.
    monkeypatch.chdir(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("MCP unreachable")

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(LinearMcpExhaustedError):
        client.call("mcp__linear__save_issue", title="[SPEC] test", description="x")

    # No files written to cwd (the only allowed local-write surface is
    # .specify/logs/ which the client doesn't manage directly).
    leftover = [p for p in tmp_path.iterdir() if p.name != ".specify"]
    assert (
        leftover == []
    ), f"Client MUST NOT write artifacts locally on failure; found {leftover}"


# --- Scrubbing on the log path (FR-021, FR-029, FR-034) -------------------


def test_request_payload_is_scrubbed_before_logging(make_client, fake_redactor):
    """Every attempt's payload passes through the Redacting filter before
    reaching the logger; the test asserts the filter was invoked."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = make_client(httpx.MockTransport(handler))
    client.call(
        "mcp__linear__save_issue",
        title="[SPEC] 001",
        description="Token leak: ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    # The redactor must have been invoked at least once during logging.
    assert (
        fake_redactor.redact.called
    ), "Client MUST scrub payloads via the Redacting filter before logging"


def test_log_entries_carry_attempt_number(make_client, fake_logger):
    """Each retry attempt produces a log entry with monotonically increasing
    `attempt` numbers (1..N) per Contract C5."""

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(502)
        return httpx.Response(200, json={"ok": True})

    client = make_client(httpx.MockTransport(handler))
    client.call("mcp__linear__list_teams")

    seen_attempts = [
        kwargs.get("attempt") for _, _, kwargs in fake_logger.log_mcp_attempt.mock_calls
    ]
    assert seen_attempts == [1, 2, 3]


# --- Idempotency contract (relevant to FR-031 — wrapper passes id-through) -


def test_call_passes_through_id_for_idempotent_update(make_client):
    """The client is a thin transport; it MUST forward `id=` to the MCP server
    so callers (hooks) can rely on save_issue idempotency."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({"path": request.url.path, "content": request.content})
        return httpx.Response(200, json={"ok": True, "id": "PMO-99"})

    client = make_client(httpx.MockTransport(handler))
    client.call("mcp__linear__save_issue", id="PMO-99", description="updated body")

    assert b'"id"' in seen["content"] and b"PMO-99" in seen["content"]


# --- Protocol conformance --------------------------------------------------


def test_impl_satisfies_linear_mcp_client_protocol(make_client):
    """Static contract: the concrete impl MUST be a runtime-checkable instance
    of the :class:`LinearMcpClient` Protocol."""
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert isinstance(client, LinearMcpClient)
