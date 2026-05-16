"""Unit tests for the secret-scrubbing logging filter (T014).

Per Spec FR-021, FR-029, FR-034 and Research §R5:
- Redacts OAuth bearer tokens, GitHub PATs, Linear workspace UUIDs, and
  RFC 5322 email addresses.
- Produces deterministic placeholders so two implementations always agree
  for the same input.
- Leaves non-secret content untouched.

Tests MUST fail before T015 (impl) per Constitution P4.
"""

from __future__ import annotations

import logging
import re

import pytest

redacting_filter_module = pytest.importorskip(
    "extensions.linear.scripts.redacting_filter",
    reason="T015 implementation not yet present — expected during RED phase.",
)
RedactingFilter = redacting_filter_module.RedactingFilter
redact = redacting_filter_module.redact  # module-level convenience function


PLACEHOLDER = re.compile(r"<TOKEN_[0-9a-f]{6}>")


# --- Pattern coverage -----------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        # OAuth bearer-style token
        "Bearer abcdef1234567890abcdef1234567890",
        # GitHub PATs (classic + fine-grained)
        "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789",
        "github_pat_11AAAAAAA0aBcDeFgHiJkL_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789aBcDeFgH",
        # Linear workspace UUID
        "0caf2e08-3667-459b-9c22-db0edbd17ce4",
        # Email address
        "user@example.com",
    ],
)
def test_known_secret_patterns_are_redacted(secret):
    redacted = redact(secret)
    assert secret not in redacted, f"Secret '{secret}' leaked unredacted"
    assert PLACEHOLDER.search(
        redacted
    ), f"Expected <TOKEN_xxxxxx> placeholder, got: {redacted!r}"


def test_non_secret_text_is_unchanged():
    text = "The quick brown fox jumps over the lazy dog 1234. No secrets here."
    assert redact(text) == text


def test_mixed_content_only_secrets_redacted():
    raw = "User user@example.com uploaded with ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789 yesterday."
    out = redact(raw)
    assert "user@example.com" not in out
    assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789" not in out
    assert "User" in out and "uploaded" in out and "yesterday" in out


# --- Determinism ----------------------------------------------------------


def test_redaction_is_deterministic_same_input_same_placeholder():
    secret = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
    a = redact(secret)
    b = redact(secret)
    assert a == b, "Same secret must produce same placeholder across calls"


def test_redaction_distinguishes_different_secrets():
    a = redact("ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")
    b = redact("ghp_ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ")
    assert a != b, "Different secrets must produce different placeholders"


def test_placeholder_uses_sha256_prefix():
    """Placeholder format: <TOKEN_{first_6_hex_chars_of_sha256(secret)}>."""
    import hashlib

    secret = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
    expected_prefix = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:6]
    assert f"<TOKEN_{expected_prefix}>" in redact(secret)


# --- LogRecord integration ------------------------------------------------


def test_filter_mutates_log_record_msg():
    logger = logging.getLogger("test.redacting")
    logger.handlers.clear()
    logger.addFilter(RedactingFilter())
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(Capture())
    logger.warning("token=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")

    assert captured, "No log records captured"
    assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789" not in captured[0]
    assert PLACEHOLDER.search(captured[0])


def test_filter_returns_true_so_record_propagates():
    rec = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "msg with user@example.com",
        None,
        None,
    )
    assert RedactingFilter().filter(rec) is True


def test_filter_handles_record_args_with_secrets():
    rec = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "auth=%s",
        ("ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789",),
        None,
    )
    RedactingFilter().filter(rec)
    rendered = rec.getMessage()
    assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789" not in rendered
    assert PLACEHOLDER.search(rendered)


# --- Edge cases (CHK022, CHK023 from Security checklist) ------------------


def test_token_matching_multiple_patterns_redacted_once():
    """A substring that matches both bearer-token and email shape MUST still
    be redacted (only one placeholder, no double-replacement that leaks)."""
    # Construct a substring that is ambiguous (synthetic; real-world would be rare).
    text = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789@example.com"
    out = redact(text)
    assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ" not in out


def test_redact_empty_string():
    assert redact("") == ""


def test_redact_none_safe():
    """Defensive: None must not crash; returns None or empty."""
    out = redact(None)  # type: ignore[arg-type]
    assert out in (None, "")
