"""Tests for stack trace capture in query_doctor.stack_tracer."""

from __future__ import annotations

from query_doctor.stack_tracer import capture_callsite
from query_doctor.types import CallSite


class TestCaptureCallsite:
    """Tests for capture_callsite()."""

    def test_returns_callsite(self) -> None:
        """capture_callsite should return a CallSite from this test file."""
        result = capture_callsite()
        assert result is not None
        assert isinstance(result, CallSite)

    def test_captures_this_file(self) -> None:
        """The callsite should point to this test file."""
        result = capture_callsite()
        assert result is not None
        assert "test_stack_tracer" in result.filepath

    def test_captures_correct_function(self) -> None:
        """The callsite should capture the calling function name."""
        result = capture_callsite()
        assert result is not None
        assert result.function_name == "test_captures_correct_function"

    def test_captures_line_number(self) -> None:
        """The callsite should have a positive line number."""
        result = capture_callsite()
        assert result is not None
        assert result.line_number > 0

    def test_filters_query_doctor_frames(self) -> None:
        """Frames from query_doctor itself should be filtered out."""
        result = capture_callsite()
        assert result is not None
        assert "query_doctor" not in result.filepath or "test" in result.filepath

    def test_exclude_modules(self) -> None:
        """Custom exclude_modules should filter out matching frames."""
        # Exclude this test module — should still find a frame (pytest runner)
        result = capture_callsite(exclude_modules=["test_stack_tracer"])
        # Should either return None or a different file
        if result is not None:
            assert "test_stack_tracer" not in result.filepath

    def test_never_crashes(self) -> None:
        """capture_callsite should never raise an exception."""
        # Even with aggressive exclusions, it should return None, not crash
        result = capture_callsite(exclude_modules=["everything"])
        # Just assert no exception was raised
        assert result is None or isinstance(result, CallSite)

    def test_nested_call_captures_outer(self) -> None:
        """When called from a nested function, captures the user-code frame."""

        def inner_function() -> CallSite | None:
            return capture_callsite()

        result = inner_function()
        assert result is not None
        assert "test_stack_tracer" in result.filepath
