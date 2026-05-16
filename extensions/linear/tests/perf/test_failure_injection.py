"""SC-010 verification: ≥99% command success under 10% transient-failure
injection rate (T073).

This is a deterministic test — the FailureInjector is seeded so failures
fall in a predictable pattern; the LinearMcpClient's bounded-retry policy
must absorb them.
"""

from __future__ import annotations

import pytest

from extensions.linear.scripts.failure_injection import (
    FailureInjector,
    make_injecting_logger,
    make_injecting_transport,
)
from extensions.linear.scripts.linear_mcp_client import LinearMcpClientImpl
from extensions.linear.scripts.protocols import LinearMcpExhaustedError
from extensions.linear.scripts.redacting_filter import redact


class _StubRedactor:
    def redact(self, text: str) -> str:
        return redact(text)


@pytest.mark.parametrize("seed", [1, 7, 42, 314, 2718])
def test_99pct_success_under_10pct_injection(seed: int) -> None:
    """1000-call sweep with p=0.10 transient injection: ≥99% commands succeed.

    Each "command" is modeled as a single MCP call against an injecting
    transport. The bounded-retry policy (3 attempts) compensates for
    isolated injections. A command fails only when 3 consecutive attempts
    all draw a transient status, which at p=0.10 happens at rate
    p^3 = 0.001, well below the 1% failure budget.
    """
    injector = FailureInjector(probability=0.10, seed=seed)
    transport = make_injecting_transport(injector=injector)
    logger = make_injecting_logger()

    client = LinearMcpClientImpl(
        base_url="https://mcp.linear.app/mcp",
        transport=transport,
        logger=logger,
        redactor=_StubRedactor(),
        max_attempts=3,
        initial_backoff_seconds=0.0,  # speed up
        jitter_percent=0.0,
        transient_http_statuses=(429, 500, 502, 503, 504),
    )

    n = 1000
    successes = 0
    exhausted = 0
    for _ in range(n):
        try:
            client.call("mcp__linear__list_teams")
            successes += 1
        except LinearMcpExhaustedError:
            exhausted += 1

    success_rate = successes / n
    assert success_rate >= 0.99, (
        f"SC-010 violated: success rate {success_rate:.3%} with seed={seed} "
        f"({successes} ok / {exhausted} exhausted / {n} total). "
        f"Actual injection rate: {injector.injection_rate:.3%}."
    )
    # Sanity: the actual injection rate should be near the configured 10%.
    assert (
        0.05 <= injector.injection_rate <= 0.15
    ), f"Injector misconfigured? Actual rate {injector.injection_rate:.3%}, expected ~10%"


def test_injector_seed_is_deterministic() -> None:
    a = FailureInjector(probability=0.5, seed=123)
    b = FailureInjector(probability=0.5, seed=123)
    seq_a = [a.should_inject() for _ in range(20)]
    seq_b = [b.should_inject() for _ in range(20)]
    assert seq_a == seq_b, "Same seed must produce same injection sequence"


def test_injection_rate_property() -> None:
    inj = FailureInjector(probability=1.0, seed=0)
    for _ in range(100):
        inj.should_inject()
    assert inj.injection_rate == 1.0
