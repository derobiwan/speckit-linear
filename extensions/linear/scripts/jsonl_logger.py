"""Structured JSON-Lines rotating-file logger (T017).

Implements :class:`JsonLinesLogger` Protocol from
:mod:`extensions.linear.scripts.protocols`. Writes one JSON object per line
to ``<log_dir>/linear-mcp.log`` with size-based rotation (10 MB / 5 backups
by default, configurable). Pipes every record through
:class:`RedactingFilter` so secrets never reach disk.

Honors ``SPECIFY_VERBOSITY`` env var for stderr level:
  - ``"0"`` or unset → ``WARNING``
  - ``"1"``          → ``INFO``
  - ``"2"`` or more  → ``DEBUG``

Satisfies Contract C5 and Spec FR-034.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from extensions.linear.scripts.redacting_filter import RedactingFilter, redact

__all__ = ["get_logger", "JsonLinesLoggerImpl"]


_LEVEL_BY_VERBOSITY: dict[str, str] = {
    "": "WARN",
    "0": "WARN",
    "1": "INFO",
    "2": "DEBUG",
}


def _stderr_level_from_env() -> str:
    verbosity = os.environ.get("SPECIFY_VERBOSITY", "0")
    if verbosity not in _LEVEL_BY_VERBOSITY:
        # 3+ folds to DEBUG.
        return "DEBUG"
    return _LEVEL_BY_VERBOSITY[verbosity]


def _now_iso_ms() -> str:
    """ISO 8601 UTC with millisecond precision, ending in 'Z'."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class _JsonLinesFormatter(logging.Formatter):
    """Renders structured log records as compact JSON Lines.

    Reads extra fields from ``record.__dict__['_payload']`` (a dict) and
    merges them on top of the base record fields.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = getattr(record, "_payload", {}) or {}
        msg = redact(record.getMessage())
        # Normalize Python's "WARNING" to Contract C5's "WARN".
        level_name = record.levelname
        if level_name == "WARNING":
            level_name = "WARN"
        entry: dict[str, Any] = {
            "ts": _now_iso_ms(),
            "lvl": level_name,
            "cmd": payload.get("cmd", record.name),
            "phase": payload.get("phase", "log"),
            "msg": msg,
        }
        for opt in ("tool", "attempt", "http", "dur_ms", "req_id"):
            if opt in payload and payload[opt] is not None:
                entry[opt] = payload[opt]
        if "preview" in payload and payload["preview"] is not None:
            preview = redact(str(payload["preview"]))
            entry["preview"] = preview[:200]
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=False)


class JsonLinesLoggerImpl:
    """Concrete :class:`JsonLinesLogger`.

    Owns a private :class:`logging.Logger` configured with a file handler
    (JSON Lines, rotated) and a stderr handler (human-readable, level
    controlled by ``SPECIFY_VERBOSITY``).
    """

    def __init__(
        self,
        log_dir: Path,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "linear-mcp.log"
        self.stderr_level_name = _stderr_level_from_env()

        logger_name = f"speckit.linear.mcp.{id(self)}"
        self._logger = logging.getLogger(logger_name)
        self._logger.handlers.clear()
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # File handler — JSON Lines, rotated, scrubbed.
        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_JsonLinesFormatter())
        file_handler.addFilter(RedactingFilter())
        self._logger.addHandler(file_handler)

        # Stderr handler — human-readable, controlled by SPECIFY_VERBOSITY.
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(
            getattr(
                logging,
                "WARNING"
                if self.stderr_level_name == "WARN"
                else self.stderr_level_name,
            )
        )
        stderr_handler.setFormatter(
            logging.Formatter("[linear] %(levelname)s %(message)s")
        )
        stderr_handler.addFilter(RedactingFilter())
        self._logger.addHandler(stderr_handler)

    def close(self) -> None:
        """Detach and close every handler.

        Without this, the file handle opened by ``RotatingFileHandler``
        outlives the logger instance and triggers a ``ResourceWarning``
        when the GC eventually reclaims it — visible under pytest's
        ``-W error`` mode and in any short-lived caller pattern (tests,
        one-shot CLI invocations). Production long-running processes
        don't observe the leak in practice because the logger lives for
        the process lifetime, but the fix is cheap and makes the test
        suite warning-clean.
        """
        for handler in list(self._logger.handlers):
            self._logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                # Best-effort: never let a logger teardown break a caller.
                pass

    def __enter__(self) -> "JsonLinesLoggerImpl":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        # Backstop in case a caller forgets to close. We swallow
        # everything because __del__ shouldn't raise during interpreter
        # shutdown (handlers may already be gone).
        try:
            self.close()
        except Exception:
            pass

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
    ) -> None:
        py_level = getattr(
            logging, "WARNING" if level == "WARN" else level, logging.INFO
        )
        payload = {
            "cmd": cmd,
            "phase": "mcp_call",
            "tool": tool,
            "attempt": attempt,
            "http": http_status,
            "dur_ms": duration_ms,
            "req_id": request_id,
            "preview": preview,
        }
        record = self._logger.makeRecord(
            name=self._logger.name,
            level=py_level,
            fn=__file__,
            lno=0,
            msg=message,
            args=None,
            exc_info=None,
        )
        record._payload = payload  # type: ignore[attr-defined]
        self._logger.handle(record)


def get_logger(
    log_dir: Path | str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> JsonLinesLoggerImpl:
    """Construct a configured logger instance.

    The implementation is process-local; tests pass a temp directory.
    Production callers will pass ``.specify/logs/`` from linear-config.yml.
    """
    return JsonLinesLoggerImpl(
        log_dir=Path(log_dir),
        max_bytes=max_bytes,
        backup_count=backup_count,
    )
