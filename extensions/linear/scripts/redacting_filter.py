"""Secret-scrubbing logging filter (T015).

Implements the :class:`Redacting` and :class:`RedactingLogFilter` Protocols
from :mod:`extensions.linear.scripts.protocols`. Replaces secret-shaped
substrings with deterministic placeholders of the form
``<TOKEN_xxxxxx>`` where ``xxxxxx`` is the first 6 hex chars of the SHA-256
of the original substring.

Satisfies Spec FR-021, FR-029, FR-034 (scrubbing leg). Research §R5.

Two integration points:
- :func:`redact` — pure function, callable directly.
- :class:`RedactingFilter` — :class:`logging.Filter` subclass; mutates
  ``record.msg`` and any string args before downstream handlers see them.
"""

from __future__ import annotations

import hashlib
import logging
import re

__all__ = ["redact", "RedactingFilter"]


# Pattern table — order matters: longer/more specific patterns first so a
# substring matching multiple rules collapses to one placeholder rather than
# producing a partial replacement (CHK022/CHK023 in Security checklist).
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # GitHub fine-grained PATs (longest, prefix github_pat_)
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    # GitHub classic PATs and other ghp_/ghs_/gho_/ghu_/ghr_ tokens.
    re.compile(r"gh[opsur]_[A-Za-z0-9_]+"),
    # OAuth bearer tokens — "Bearer <opaque-base64ish>".
    re.compile(r"Bearer\s+[A-Za-z0-9+/=._-]+"),
    # Linear workspace / object UUIDs (RFC 4122).
    re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    # RFC 5322-ish email addresses (intentionally permissive).
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


def _placeholder(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:6]
    return f"<TOKEN_{digest}>"


def redact(text: str | None) -> str:
    """Return ``text`` with every recognised secret replaced.

    ``None`` and empty strings pass through safely (return the same).
    """
    if text is None:
        return ""
    if not text:
        return text
    out = text
    for pattern in _PATTERNS:
        out = pattern.sub(lambda m: _placeholder(m.group(0)), out)
    return out


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs every record before it reaches a handler.

    Mutates :attr:`logging.LogRecord.msg` and stringifies+scrubs every
    string item in :attr:`logging.LogRecord.args` so handlers using either
    :py:meth:`logging.LogRecord.getMessage` or the raw fields see redacted
    text only.

    Always returns ``True`` — records are never dropped.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 — stdlib signature
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _scrub(v) for k, v in record.args.items()}
            else:
                record.args = tuple(_scrub(a) for a in record.args)
        return True


def _scrub(value: object) -> object:
    if isinstance(value, str):
        return redact(value)
    return value
