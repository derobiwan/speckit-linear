"""Unit tests for the structured JSON-Lines rotating-file logger (T016).

Asserts Contract C5 and Spec FR-034:
- Every line is valid JSON.
- Required fields: ts, lvl, cmd, phase, msg.
- ISO 8601 UTC with millisecond precision.
- File rotates at 10 MB, keeps 5 backups.
- Stderr level honors SPECIFY_VERBOSITY env var (0=WARN, 1=INFO, 2=DEBUG).
- Pre-scrub patterns never appear in msg (RedactingFilter integration).

Tests MUST fail before T017 (impl) per Constitution P4.
"""

from __future__ import annotations

import json
import re

import pytest

jsonl_logger_module = pytest.importorskip(
    "extensions.linear.scripts.jsonl_logger",
    reason="T017 implementation not yet present — expected during RED phase.",
)
get_logger = jsonl_logger_module.get_logger


ISO_8601_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@pytest.fixture()
def log_dir(tmp_path):
    return tmp_path / "logs"


@pytest.fixture(autouse=True)
def _close_loggers_after_test():
    """Close every JsonLinesLoggerImpl created during the test.

    Without this, the ``RotatingFileHandler`` opened in ``__init__`` lives
    past the test's tmp-dir teardown and surfaces as ``ResourceWarning:
    unclosed file ...``. The logger class is a context manager and has
    a ``close()`` method; we use both signals to find live instances by
    walking the ``logging.Logger.manager`` dict.
    """
    yield
    import logging

    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("speckit.linear.mcp."):
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass


def _read_lines(log_path):
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line
    ]


# --- Schema (Contract C5) -------------------------------------------------


def test_emits_valid_jsonlines(log_dir):
    logger = get_logger(log_dir=log_dir)
    logger.log_mcp_attempt(
        cmd="speckit.specify",
        tool="mcp__linear__list_teams",
        attempt=1,
        http_status=200,
        duration_ms=142,
        request_id="req_abc",
        message="discover team",
    )
    lines = _read_lines(log_dir / "linear-mcp.log")
    assert len(lines) == 1
    entry = lines[0]
    for required in ("ts", "lvl", "cmd", "phase", "msg"):
        assert required in entry, f"Required field {required} missing: {entry}"


def test_timestamp_is_iso8601_utc_ms_precision(log_dir):
    logger = get_logger(log_dir=log_dir)
    logger.log_mcp_attempt(
        cmd="speckit.specify",
        tool="t",
        attempt=1,
        http_status=200,
        duration_ms=1,
        request_id="r",
        message="m",
    )
    entry = _read_lines(log_dir / "linear-mcp.log")[0]
    assert ISO_8601_MS.match(entry["ts"]), f"Bad timestamp: {entry['ts']}"


def test_optional_fields_round_trip(log_dir):
    logger = get_logger(log_dir=log_dir)
    logger.log_mcp_attempt(
        cmd="speckit.plan",
        tool="mcp__linear__save_issue",
        attempt=2,
        http_status=503,
        duration_ms=214,
        request_id="req_xyz",
        message="transient 503; will retry",
        preview="{title: ...}",
        level="WARN",
    )
    entry = _read_lines(log_dir / "linear-mcp.log")[0]
    assert entry["tool"] == "mcp__linear__save_issue"
    assert entry["attempt"] == 2
    assert entry["http"] == 503
    assert entry["dur_ms"] == 214
    assert entry["req_id"] == "req_xyz"
    assert entry["preview"] == "{title: ...}"
    assert entry["lvl"] == "WARN"


def test_phase_default_is_mcp_call_for_log_mcp_attempt(log_dir):
    logger = get_logger(log_dir=log_dir)
    logger.log_mcp_attempt(
        cmd="speckit.specify",
        tool="t",
        attempt=1,
        http_status=200,
        duration_ms=1,
        request_id=None,
        message="m",
    )
    entry = _read_lines(log_dir / "linear-mcp.log")[0]
    assert entry["phase"] == "mcp_call"


# --- Rotation (FR-034) ----------------------------------------------------


def test_rotation_kicks_in_at_10mb(log_dir, monkeypatch):
    """Rotate when file exceeds 10 MB; keep 5 backups."""
    # Use a much smaller threshold for test speed; the real impl reads
    # the limit from config so the test injects a small value.
    logger = get_logger(log_dir=log_dir, max_bytes=1024, backup_count=5)
    # Write enough log entries to exceed the threshold.
    for i in range(50):
        logger.log_mcp_attempt(
            cmd="speckit.specify",
            tool="mcp__linear__save_issue",
            attempt=1,
            http_status=200,
            duration_ms=1,
            request_id=f"req_{i:04d}",
            message="x" * 200,
        )
    rotations = sorted(p.name for p in log_dir.iterdir())
    # Expect linear-mcp.log + at least one rotation (.1)
    assert "linear-mcp.log" in rotations
    assert any(
        name.startswith("linear-mcp.log.") for name in rotations
    ), f"Expected rotation, got: {rotations}"


def test_rotation_keeps_at_most_5_backups(log_dir):
    logger = get_logger(log_dir=log_dir, max_bytes=512, backup_count=5)
    for i in range(200):
        logger.log_mcp_attempt(
            cmd="speckit.specify",
            tool="mcp__linear__save_issue",
            attempt=1,
            http_status=200,
            duration_ms=1,
            request_id=f"req_{i:04d}",
            message="x" * 200,
        )
    backups = [p for p in log_dir.iterdir() if p.name.startswith("linear-mcp.log.")]
    assert (
        len(backups) <= 5
    ), f"Rotation MUST keep at most 5 backups; found {len(backups)}: {[b.name for b in backups]}"


# --- Scrubbing integration (FR-029, FR-034) -------------------------------


def test_message_never_contains_pre_scrub_pattern(log_dir):
    logger = get_logger(log_dir=log_dir)
    logger.log_mcp_attempt(
        cmd="speckit.specify",
        tool="mcp__linear__save_issue",
        attempt=1,
        http_status=200,
        duration_ms=1,
        request_id="r",
        message="user user@example.com wrote x",
    )
    line = (log_dir / "linear-mcp.log").read_text(encoding="utf-8")
    assert (
        "user@example.com" not in line
    ), "Logger MUST scrub all pre-scrub patterns before writing"
    assert "<TOKEN_" in line


def test_preview_truncated_to_200_chars(log_dir):
    logger = get_logger(log_dir=log_dir)
    logger.log_mcp_attempt(
        cmd="speckit.specify",
        tool="t",
        attempt=1,
        http_status=200,
        duration_ms=1,
        request_id=None,
        message="m",
        preview="x" * 500,
        level="DEBUG",
    )
    entry = _read_lines(log_dir / "linear-mcp.log")[0]
    assert len(entry["preview"]) <= 200


# --- Stderr verbosity via env var ----------------------------------------


@pytest.mark.parametrize(
    "verbosity,expected_level",
    [("0", "WARN"), ("1", "INFO"), ("2", "DEBUG"), ("", "WARN")],
)
def test_verbosity_env_var_maps_to_level(
    log_dir, monkeypatch, verbosity, expected_level
):
    monkeypatch.setenv("SPECIFY_VERBOSITY", verbosity)
    logger = get_logger(log_dir=log_dir)
    assert logger.stderr_level_name == expected_level
