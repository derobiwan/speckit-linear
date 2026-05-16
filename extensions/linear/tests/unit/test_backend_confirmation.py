"""T053 — Backend confirmation line (FR-022).

Every Linear-preset-active command MUST emit exactly one line to
**stderr** before any artifact-writing MCP call:

    [linear] backend=Linear workspace=<team-name> project=<project-name>

Implementation lives in
:func:`extensions.linear.scripts.hook_helpers.emit_backend_line`. The
function takes the resolved workspace + project names and writes to
``sys.stderr``. Each before-hook invokes it once.

Tests cover:

* Format conformance (exact prefix + key=value pairs).
* Idempotency-per-invocation — calling the helper twice in a row in
  the same run still produces a single line (the helper enforces a
  per-process sentinel).
* Ordering — the line lands on stderr before the first ``save_*`` MCP
  call when wired into a hook (fake MCP records the order).
* Quoting — workspace / project names with spaces remain readable
  (no shell-style escaping; we wrap in single quotes when whitespace
  appears).
"""

from __future__ import annotations

import io
import sys
from typing import Any

import pytest

helpers = pytest.importorskip(
    "extensions.linear.scripts.hook_helpers",
    reason="T027 must provide hook_helpers before this test can run.",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_emit_sentinel():
    """Each test starts with the per-process emission sentinel cleared."""
    if hasattr(helpers, "_BACKEND_LINE_EMITTED"):
        helpers._BACKEND_LINE_EMITTED.clear()  # type: ignore[attr-defined]
    yield
    if hasattr(helpers, "_BACKEND_LINE_EMITTED"):
        helpers._BACKEND_LINE_EMITTED.clear()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------


class TestSurface:
    def test_emit_backend_line_is_exported(self) -> None:
        assert hasattr(
            helpers, "emit_backend_line"
        ), "T053: hook_helpers must expose ``emit_backend_line(workspace, project, *, stream=sys.stderr)``"
        assert callable(helpers.emit_backend_line)


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------


class TestLineFormat:
    def test_line_uses_documented_prefix(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        helpers.emit_backend_line(workspace="Acme", project="My Product")
        out = capsys.readouterr()
        assert out.err.startswith(
            "[linear] backend=Linear "
        ), f"Expected '[linear] backend=Linear ' prefix; got {out.err!r}"

    def test_line_includes_workspace_and_project(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        out = capsys.readouterr()
        assert "workspace=Acme" in out.err
        assert "project=MyProduct" in out.err

    def test_line_quotes_values_with_whitespace(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        helpers.emit_backend_line(workspace="Big Co", project="My Product")
        out = capsys.readouterr()
        assert (
            "workspace='Big Co'" in out.err
        ), f"Whitespace-containing workspace must be single-quoted: {out.err!r}"
        assert "project='My Product'" in out.err

    def test_line_goes_to_stderr_not_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        out = capsys.readouterr()
        assert out.out == "", f"stdout should be empty; got {out.out!r}"
        assert out.err.strip(), "stderr must contain the confirmation line"

    def test_line_has_trailing_newline(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        out = capsys.readouterr()
        assert out.err.endswith("\n"), "confirmation line must terminate with a newline"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_call_within_run_is_silent(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        out = capsys.readouterr()
        assert (
            out.err.count("[linear] backend=Linear") == 1
        ), f"Second call must be a no-op; got:\n{out.err}"

    def test_different_target_re_emits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A change in target re-emits — hooks chained across features need it."""
        helpers.emit_backend_line(workspace="Acme", project="ProductA")
        helpers.emit_backend_line(workspace="Acme", project="ProductB")
        out = capsys.readouterr()
        assert (
            out.err.count("[linear] backend=Linear") == 2
        ), f"Distinct workspace/project must re-emit; got:\n{out.err}"


# ---------------------------------------------------------------------------
# Ordering — fired before MCP writes
# ---------------------------------------------------------------------------


class TestOrdering:
    def test_emit_before_save_calls(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wire emit_backend_line as a pre-step around a fake MCP `save_*`."""
        log: list[str] = []

        class FakeMcp:
            def call(self, tool: str, payload: dict) -> dict[str, Any]:
                log.append(tool)
                # Capture whether stderr already has the line at this point.
                err_now = (
                    sys.stderr.getvalue() if isinstance(sys.stderr, io.StringIO) else ""
                )
                log.append(f"err-len:{len(err_now)}")
                return {"id": "id_1"}

        # Replace stderr with a buffer we can inspect mid-flight.
        buf = io.StringIO()
        monkeypatch.setattr("sys.stderr", buf)

        helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        FakeMcp().call("mcp__linear__save_issue", {"title": "x"})

        # Confirmation line must already be in the buffer when save fired.
        first_tool_index = log.index("mcp__linear__save_issue")
        snapshot_len_after_tool = int(log[first_tool_index + 1].split(":")[1])
        assert (
            snapshot_len_after_tool > 0
        ), f"Confirmation line not written before save_*; log={log!r} buf={buf.getvalue()!r}"
        assert "[linear] backend=Linear" in buf.getvalue()
