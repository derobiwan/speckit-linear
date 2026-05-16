"""Transient-failure injection harness (T073).

Wraps a :class:`LinearMcpClient` so that, with a configurable per-call
probability, the call returns one of the listed transient HTTP statuses
instead of executing for real. Used by the SC-010 verification test:
under a 10% injection rate, ≥99% of commands must still succeed (because
the LinearMcpClient's bounded-retry policy absorbs transient failures).

Implementation note: this is test infrastructure, not production code.
It's imported only from ``extensions/linear/tests/perf/`` and from any
end-to-end stress test that needs to validate the retry policy's effect
on overall command success rate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import httpx

__all__ = ["FailureInjector", "make_injecting_transport"]


@dataclass
class FailureInjector:
    """Decision-making side of the harness.

    Holds the random state (seeded for reproducibility) and tracks the
    history of injection decisions for post-hoc test assertions.
    """

    probability: float = 0.10
    statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    seed: int = 0
    history: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(f"probability must be in [0,1], got {self.probability}")
        self._rng = random.Random(self.seed)

    def should_inject(self) -> tuple[bool, int]:
        """Return (inject, status). If inject is False, status is undefined."""
        inject = self._rng.random() < self.probability
        self.history.append(inject)
        status = self._rng.choice(self.statuses) if inject else 200
        return inject, status

    @property
    def injection_rate(self) -> float:
        if not self.history:
            return 0.0
        return sum(self.history) / len(self.history)


def make_injecting_transport(
    delegate_responses: dict[str, dict[str, Any]] | None = None,
    *,
    injector: FailureInjector,
) -> httpx.MockTransport:
    """Build a transport that injects failures per ``injector``.

    On a non-injection turn, returns the canned success response for the
    matching tool name from ``delegate_responses``, or a generic
    ``{"ok": true}`` body if absent.
    """
    delegate_responses = delegate_responses or {}

    def handler(request: httpx.Request) -> httpx.Response:
        inject, status = injector.should_inject()
        if inject:
            return httpx.Response(
                status,
                json={"error": f"injected transient {status}"},
                headers={"x-request-id": "injected"},
            )
        # Resolve canned response by tool name (path-suffix matching).
        body = delegate_responses.get(request.url.path.rstrip("/"), {"ok": True})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def make_injecting_logger() -> MagicMock:
    """A throwaway logger suitable for the failure-injection performance test."""
    return MagicMock()
