"""Tests for stack trace capture in query_doctor.stack_tracer."""

from __future__ import annotations

import traceback
from unittest.mock import patch

import pytest

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
        # Exclude this test module -- should still find a frame (pytest runner)
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


class TestInstalledPackageLayouts:
    """Django ORM frames must be skipped regardless of install path layout.

    ``django/db/models/manager.py`` (every ``.objects.create()``) and
    ``django/db/models/base.py`` (every ``.save()``) were named nowhere in the
    exclude list and were skipped only by the ``site-packages`` substring test.
    Debian and Ubuntu system Python install to ``dist-packages``, so on those
    layouts the frames survived filtering and every prescription from a create
    or save was attributed to a line inside Django.

    These drive a synthetic stack rather than a real one so the assertion does
    not depend on where Django happens to be installed on the machine running
    the suite -- which is exactly the property that let the defect hide.
    """

    def _stack(self, *filenames: str) -> list[traceback.FrameSummary]:
        """Build a synthetic stack, outermost first."""
        return [
            traceback.FrameSummary(filename, 10 + i, f"fn{i}")
            for i, filename in enumerate(filenames)
        ]

    @pytest.mark.parametrize(
        "django_frame",
        [
            "/usr/local/lib/python3.12/dist-packages/django/db/models/manager.py",
            "/usr/local/lib/python3.12/dist-packages/django/db/models/base.py",
            "/usr/local/lib/python3.12/dist-packages/django/db/models/query.py",
            "/usr/lib/python3/dist-packages/django/db/backends/utils.py",
            # Backslash form, deliberately not under site-packages: this row
            # must exercise the "django\\db" pattern, not the install-path check.
            r"C:\vendor\django\db\models\manager.py",
        ],
    )
    def test_django_orm_frames_are_skipped(self, django_frame: str) -> None:
        """The user frame wins over a Django ORM frame closer to the query."""
        stack = self._stack("/app/myapp/views.py", django_frame)

        with patch.object(traceback, "extract_stack", return_value=stack):
            result = capture_callsite()

        assert result is not None
        assert result.filepath == "/app/myapp/views.py"

    @pytest.mark.parametrize(
        "user_frame",
        [
            "/srv/mydjango/db/models.py",
            "/srv/mydjango/dbrouters.py",
            "/app/pydjango/db/utils.py",
            # Backslash form, deliberately outside site-packages so the row
            # exercises the anchored "\\django\\db\\" pattern rather than the
            # install-path check.
            r"C:\srv\mydjango\db\models.py",
        ],
    )
    def test_user_paths_containing_the_pattern_are_returned(self, user_frame: str) -> None:
        """The exclusion is a path segment, not a bare substring.

        A project directory named ``mydjango`` with a ``db`` module inside it must
        keep its frames. Before the pattern was anchored on separators, excluding
        ``django/db`` wholesale also dropped these, and the callsite fell through
        to an outer frame or to None -- the same class of harm as attributing it
        inside Django, narrower.
        """
        stack = self._stack(user_frame)

        with patch.object(traceback, "extract_stack", return_value=stack):
            result = capture_callsite()

        assert result is not None
        assert result.filepath == user_frame

    def test_a_dist_packages_frame_alone_yields_no_callsite(self) -> None:
        """With only installed-package frames there is no user code to point at."""
        stack = self._stack(
            "/usr/local/lib/python3.12/dist-packages/django/db/models/manager.py",
        )

        with patch.object(traceback, "extract_stack", return_value=stack):
            assert capture_callsite() is None

    def test_positive_control_user_frame_is_returned(self) -> None:
        """The synthetic stack is really being read.

        Without this, a capture_callsite() that returned None for every synthetic
        stack would satisfy the tests above.
        """
        stack = self._stack("/app/myapp/views.py")

        with patch.object(traceback, "extract_stack", return_value=stack):
            result = capture_callsite()

        assert result is not None
        assert result.filepath == "/app/myapp/views.py"
        assert result.line_number == 10
