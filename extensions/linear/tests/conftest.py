"""Pytest fixtures for the Linear extension test suite (T018).

Provides:
- :func:`linear_config` — a canned :class:`LinearConfig`-shaped dict for tests
- :func:`recorded_responses_dir` — path to the cassette directory
- :func:`scrubbed_vcr` — VCR.py base configured with our RedactingFilter
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so `extensions.linear.scripts.*`
# resolves during test collection even when pytest is launched from a subdir.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture()
def linear_config():
    """Canned config matching :class:`E9 LinearConfig` (Data Model PMO-75).

    Tests that need to override individual fields can use ``dict(linear_config, ...)``.
    """
    return {
        "mcp_server": {
            "name": "linear",
            "transport": "http",
            "url": "https://mcp.linear.app/mcp",
        },
        "team": {"discovery": "auto"},
        "product_project": {
            "name": "speckit-linear-skills",
            "auto_create": False,
        },
        "labels": {
            "colors": {
                "feature": "#0EA5E9",
                "spec": "#10B981",
                "plan": "#3B82F6",
                "research": "#06B6D4",
                "data-model": "#8B5CF6",
                "contract": "#EC4899",
                "quickstart": "#F97316",
                "checklist": "#F59E0B",
                "task": "#EF4444",
                "constitution": "#7C3AED",
            },
            "required": {
                "speckit_types": [
                    "spec",
                    "plan",
                    "research",
                    "data-model",
                    "quickstart",
                    "contract",
                    "checklist",
                    "task",
                    "constitution",
                ]
            },
        },
        "find_active_feature": {
            "precedence": ["user_arg", "git_branch", "ask"],
        },
        "retry": {
            "max_attempts": 3,
            "initial_backoff_seconds": 1.0,
            "jitter_percent": 0.25,
            "transient_http_statuses": [429, 500, 502, 503, 504],
        },
        "logging": {
            "dir": ".specify/logs/",
            "max_file_mb": 10,
            "keep_rotations": 5,
        },
    }


@pytest.fixture()
def recorded_responses_dir() -> Path:
    """Directory where VCR cassettes live."""
    return Path(__file__).parent / "fixtures" / "recorded_mcp_responses"


@pytest.fixture()
def scrubbed_vcr(recorded_responses_dir):
    """A VCR.py instance pre-configured to scrub recorded payloads.

    Uses our :class:`RedactingFilter` patterns so cassettes committed to the
    repo never carry secrets (FR-021, FR-029, SC-006).
    """
    pytest.importorskip("vcr", reason="vcrpy not installed; pip install -e '.[dev]'")
    import vcr  # type: ignore[import-untyped]

    from extensions.linear.scripts.redacting_filter import redact

    def before_record_request(request):
        if request.body:
            try:
                body = (
                    request.body.decode("utf-8")
                    if isinstance(request.body, bytes)
                    else str(request.body)
                )
                request.body = (
                    redact(body).encode("utf-8")
                    if isinstance(request.body, bytes)
                    else redact(body)
                )
            except UnicodeDecodeError:
                pass
        return request

    def before_record_response(response):
        for key in ("body",):
            data = response.get(key, {})
            if isinstance(data, dict) and "string" in data:
                data["string"] = redact(data["string"])
        return response

    return vcr.VCR(
        cassette_library_dir=str(recorded_responses_dir),
        record_mode=os.environ.get("VCR_RECORD_MODE", "none"),
        match_on=["method", "scheme", "host", "port", "path", "query"],
        filter_headers=["authorization", "x-api-key"],
        before_record_request=before_record_request,
        before_record_response=before_record_response,
        serializer="yaml",
    )
