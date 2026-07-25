"""Tests for console reporter in query_doctor.reporters.console."""

from __future__ import annotations

import io

from query_doctor.reporters.console import ConsoleReporter
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


class _EncodedStream(io.StringIO):
    """A text buffer that advertises a chosen encoding to Rich's probe."""

    def __init__(self, encoding: str) -> None:
        super().__init__()
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        return self._encoding


class TestConsoleReporter:
    """Tests for ConsoleReporter."""

    def test_render_empty_report(self) -> None:
        """Empty report should still produce output."""
        reporter = ConsoleReporter()
        report = DiagnosisReport()
        output = reporter.render(report)
        assert "0" in output  # Should mention 0 queries or 0 issues

    def test_render_report_with_nplusone(self) -> None:
        """Report with N+1 prescription should show CRITICAL label."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description='N+1 detected: 47 queries for table "testapp_author"',
                    fix_suggestion="Add .select_related('author') to your queryset",
                    callsite=CallSite(
                        filepath="myapp/views.py",
                        line_number=83,
                        function_name="get_queryset",
                    ),
                    query_count=47,
                    time_saved_ms=89.0,
                ),
            ],
            total_queries=53,
            total_time_ms=127.3,
        )
        output = reporter.render(report)
        assert "CRITICAL" in output
        assert "N+1" in output or "n+1" in output.lower()
        assert "select_related" in output
        assert "author" in output
        assert "myapp/views.py" in output

    def test_render_report_with_duplicate(self) -> None:
        """Report with duplicate prescription should show WARNING label."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description='6 identical queries for table "testapp_publisher"',
                    fix_suggestion="Assign the queryset result to a variable",
                    callsite=None,
                    query_count=6,
                ),
            ],
            total_queries=10,
            total_time_ms=5.0,
        )
        output = reporter.render(report)
        assert "WARNING" in output
        assert "identical" in output.lower()

    def test_render_includes_summary(self) -> None:
        """Report should include query count and time summary."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            total_queries=53,
            total_time_ms=127.3,
        )
        output = reporter.render(report)
        assert "53" in output
        assert "127.3" in output or "127" in output

    def test_render_multiple_prescriptions(self) -> None:
        """Report with multiple prescriptions should render all of them."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for author",
                    fix_suggestion="select_related('author')",
                    callsite=None,
                    query_count=10,
                ),
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="Duplicate publisher queries",
                    fix_suggestion="Cache the result",
                    callsite=None,
                    query_count=5,
                ),
            ],
            total_queries=20,
            total_time_ms=50.0,
        )
        output = reporter.render(report)
        assert "author" in output
        assert "publisher" in output.lower() or "Duplicate" in output

    def test_render_with_callsite(self) -> None:
        """Prescription with callsite should show file:line."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="Fix it",
                    callsite=CallSite(
                        filepath="myapp/views.py",
                        line_number=42,
                        function_name="my_view",
                        code_context="books = Book.objects.all()",
                    ),
                ),
            ],
        )
        output = reporter.render(report)
        assert "myapp/views.py" in output
        assert "42" in output

    def test_report_method_prints(self, capsys) -> None:
        """report() should print to stderr."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=5)
        reporter.report(report)
        captured = capsys.readouterr()
        assert "5" in captured.err


class TestConsoleReporterPlainText:
    """Tests for the plain-text fallback rendering path."""

    def _make_prescription(
        self,
        severity: Severity = Severity.CRITICAL,
        issue_type: IssueType = IssueType.N_PLUS_ONE,
        description: str = "N+1 detected",
        fix: str = "select_related('author')",
        callsite: CallSite | None = None,
        query_count: int = 0,
        time_saved_ms: float = 0.0,
    ) -> Prescription:
        return Prescription(
            issue_type=issue_type,
            severity=severity,
            description=description,
            fix_suggestion=fix,
            callsite=callsite,
            query_count=query_count,
            time_saved_ms=time_saved_ms,
        )

    def test_plain_fallback_renders_with_prescription(self) -> None:
        """Plain text fallback path renders when Rich import fails."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription()],
            total_queries=10,
            total_time_ms=50.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "CRITICAL" in output
        assert "N+1 detected" in output
        assert "select_related" in output

    def test_plain_empty_report_shows_no_issues(self) -> None:
        """Plain text path shows 'No issues detected' for empty report."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=5, total_time_ms=10.0)
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "No issues detected" in output

    def test_plain_severity_labels(self) -> None:
        """Plain text shows correct severity labels for each level."""
        from unittest.mock import patch

        prescriptions = [
            self._make_prescription(severity=Severity.CRITICAL, description="crit issue"),
            self._make_prescription(severity=Severity.WARNING, description="warn issue"),
            self._make_prescription(severity=Severity.INFO, description="info issue"),
        ]
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=prescriptions, total_queries=30, total_time_ms=100.0
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "CRITICAL" in output
        assert "WARNING" in output
        assert "INFO" in output

    def test_plain_contains_fix_suggestion(self) -> None:
        """Plain text output includes the fix suggestion."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription(fix="Add .prefetch_related('tags')")],
            total_queries=5,
            total_time_ms=10.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "prefetch_related" in output

    def test_plain_contains_callsite(self) -> None:
        """Plain text shows file:line and function from callsite."""
        from unittest.mock import patch

        cs = CallSite(
            filepath="myapp/views.py",
            line_number=42,
            function_name="list_books",
            code_context="qs = Book.objects.all()",
        )
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription(callsite=cs)],
            total_queries=5,
            total_time_ms=10.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "myapp/views.py" in output
        assert "42" in output
        assert "list_books" in output
        assert "Book.objects.all()" in output

    def test_plain_shows_query_count_and_savings(self) -> None:
        """Plain text shows query count and estimated savings."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription(query_count=47, time_saved_ms=89.0)],
            total_queries=53,
            total_time_ms=127.3,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "47" in output
        assert "89.0" in output

    def test_plain_issue_type_in_description(self) -> None:
        """Plain text renders the description which includes issue type info."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                self._make_prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description='Duplicate query: 6 identical queries for "publisher"',
                )
            ],
            total_queries=10,
            total_time_ms=20.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "Duplicate query" in output
        assert "publisher" in output


class TestConsoleReporterRichPath:
    """Tests for the Rich rendering path."""

    def test_rich_renders_nonempty_string(self) -> None:
        """Rich rendering path returns a non-empty string."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for author",
                    fix_suggestion="select_related('author')",
                    callsite=CallSite(
                        filepath="views.py",
                        line_number=10,
                        function_name="get_qs",
                        code_context="Book.objects.all()",
                    ),
                    query_count=20,
                    time_saved_ms=50.0,
                ),
            ],
            total_queries=25,
            total_time_ms=80.0,
        )
        output = reporter._render_rich(report)
        assert len(output) > 0
        assert "author" in output

    def test_rich_empty_report(self) -> None:
        """Rich rendering with no prescriptions shows the 'No issues detected' marker.

        The prior assertion (`"No issues" in output or "0" in output`) could not
        fail: the header always contains a `0` ("Total queries: 0"), so the `or`
        branch was unconditionally true and the empty-report line at
        console.py:123-124 was effectively untested (FOLLOWUPS #15). This pins the
        actual marker, and it is the only direct _render_rich coverage of that
        branch - test_coverage_gaps.py::test_render_empty_report_content goes
        through render() and passes on _render_plain too, which emits the same
        string (console.py:190).
        """
        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=0, total_time_ms=0.0)
        output = reporter._render_rich(report)
        assert "No issues detected" in output

    def test_rich_warning_severity(self) -> None:
        """Rich rendering applies yellow style for WARNING severity."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="Dup query",
                    fix_suggestion="Cache result",
                    callsite=None,
                    query_count=3,
                ),
            ],
            total_queries=5,
            total_time_ms=10.0,
        )
        output = reporter._render_rich(report)
        assert "WARNING" in output

    def test_rich_info_severity(self) -> None:
        """Rich rendering handles INFO severity."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.MISSING_INDEX,
                    severity=Severity.INFO,
                    description="Missing index on published_date",
                    fix_suggestion="Add index",
                    callsite=None,
                ),
            ],
            total_queries=2,
            total_time_ms=5.0,
        )
        output = reporter._render_rich(report)
        assert "INFO" in output


class TestConsoleReporterGrouped:
    """Tests for the grouped rendering path."""

    def test_grouped_renders_groups(self) -> None:
        """Grouped mode renders group headers."""
        import io

        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, group_by="file_analyzer")
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for author",
                    fix_suggestion="select_related('author')",
                    callsite=CallSite(filepath="views.py", line_number=10, function_name="get_qs"),
                ),
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for publisher",
                    fix_suggestion="select_related('publisher')",
                    callsite=CallSite(filepath="views.py", line_number=20, function_name="get_qs"),
                ),
            ],
            total_queries=50,
            total_time_ms=100.0,
        )
        reporter.report(report)
        output = stream.getvalue()
        assert "grouped" in output.lower()
        assert "CRITICAL" in output

    def test_grouped_empty_report(self) -> None:
        """Grouped mode with no prescriptions shows no issues."""
        import io

        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, group_by="root_cause")
        report = DiagnosisReport(total_queries=0, total_time_ms=0.0)
        reporter.report(report)
        output = stream.getvalue()
        assert "No issues detected" in output


class TestConsoleStreamProbe:
    """The Rich renderer probes the encoding of the stream it writes to (#13).

    ``_render_rich`` built ``Console(file=None)``, which probes stdout, then
    printed the captured string to ``self._stream`` - a different stream. When
    the two encodings disagree the box characters chosen from stdout garble or
    crash on the destination. The fix probes ``self._probe_target()``, which is
    ``self._stream`` normally and the unwrapped inner stream when ``self._stream``
    is a pre-5.2 ``OutputWrapper`` whose ``encoding`` reads ``None``. The write
    target (``self._stream``) is never moved.
    """

    def test_rich_console_probes_the_destination_encoding(self) -> None:
        """The Console Rich builds carries the destination's real encoding.

        Object identity is the wrong assertion: on Django <5.2 the probe target
        is the unwrapped inner stream, not ``self._stream``. And an identity
        check against ``_probe_target()`` would pass as ``None is None`` if the
        method ever regressed to returning ``None`` - reconstructing the entry-13
        bug the test exists to catch (entry 15's failure mode). Pinning the
        encoding fails on ``None``, on ``sys.stdout``, and on an un-unwrapped
        pre-5.2 ``OutputWrapper``. The wrapped encoding is cp1252 on every Django
        version: delegated on >=5.2, reached via the ``_out`` unwrap below it.
        """
        from unittest import mock

        import rich.console as rc
        from django.core.management.base import OutputWrapper

        destination = OutputWrapper(_EncodedStream("cp1252"))
        reporter = ConsoleReporter(stream=destination)

        captured: dict[str, object] = {}
        real_console = rc.Console

        def spy(*args: object, **kwargs: object) -> object:
            captured["file"] = kwargs.get("file")
            return real_console(*args, **kwargs)

        # Empty report: no prescriptions, so the RichConsole isinstance path in
        # _render_rich_prescription is not exercised and the spy stays clean.
        with mock.patch("rich.console.Console", side_effect=spy):
            reporter._render_rich(DiagnosisReport(total_queries=0, total_time_ms=0.0))

        assert getattr(captured["file"], "encoding", None) == "cp1252"
        # The renderer must not move the write target while resolving the probe.
        assert reporter._stream is destination

    def test_probe_target_exposes_wrapped_encoding_across_django(self) -> None:
        """_probe_target reaches the wrapped encoding on every supported Django.

        Pre-5.2 ``OutputWrapper`` subclasses ``TextIOBase``, so ``encoding`` reads
        ``None`` and ``__getattr__`` never forwards; >=5.2 it forwards directly.
        Either way the probe target must expose the wrapped cp1252 encoding - the
        MRO differs across the 5.2 boundary but the resolved encoding must not.
        (Replaces an assertion that ``OutputWrapper.__mro__`` is
        ``['OutputWrapper', 'object']``, which is false below 5.2.)
        """
        from django.core.management.base import OutputWrapper

        wrapped = OutputWrapper(_EncodedStream("cp1252"))
        reporter = ConsoleReporter(stream=wrapped)
        probe = reporter._probe_target()
        assert getattr(probe, "encoding", None) == "cp1252"

        # Positive control: a plain stream carrying its own encoding is returned
        # unchanged - the guard unwraps only when encoding reads None, so it does
        # not flatten well-behaved streams.
        plain = _EncodedStream("utf-8")
        assert ConsoleReporter(stream=plain)._probe_target() is plain

        # Positive control 2: a stream whose encoding reads None but which has no
        # _out to unwrap must be returned unchanged - the guard unwraps only when
        # an inner stream exists, so it never returns None for an exotic stream.
        class _NoOutStream:
            encoding = None

            def write(self, s: str) -> int:
                return len(s)

            def flush(self) -> None:
                return None

        no_out = _NoOutStream()
        assert ConsoleReporter(stream=no_out)._probe_target() is no_out


class TestRichBoxEncodingBranch:
    """The Rich renderer's ASCII-box branch, forced deterministically (FOLLOWUPS #12).

    Measured on rich 15.0.0: the pure-ASCII box substitution is driven by the
    destination stream's ENCODING (a non-utf encoding cannot represent U+2500-
    range box drawing, so Rich substitutes box.ASCII), NOT by legacy_windows.
    legacy_windows only swaps rounded corners for square ones among Unicode
    boxes. Entry 12's original "legacy_windows triggers ASCII" reading conflated
    the two because that session was also cp1252.

    After the #13 fix the encoding comes from self._stream, so forcing the
    destination stream's encoding forces the branch - deterministically, on every
    platform and every CI run, with no dependence on the host console. These
    tests would fail against the pre-#13 Console(file=None), which ignored the
    destination encoding and probed stdout instead.
    """

    def test_non_utf_destination_renders_pure_ascii_box(self) -> None:
        """A cp1252 destination makes _render_rich emit no box-drawing codepoints."""
        reporter = ConsoleReporter(stream=_EncodedStream("cp1252"))
        output = reporter._render_rich(DiagnosisReport(total_queries=0, total_time_ms=0.0))

        assert not any(ord(ch) >= 0x2500 for ch in output)  # no Unicode box drawing
        assert "No issues detected" in output  # positive control: it did render

    def test_utf8_destination_renders_unicode_box(self) -> None:
        """A utf-8 destination makes _render_rich emit Unicode box drawing.

        Asserts the horizontal (U+2500) and vertical (U+2502) rules, which are
        present in both the rounded (non-legacy) and square (legacy) Unicode
        boxes, so this holds on Linux CI and a legacy-Windows host alike.
        """
        reporter = ConsoleReporter(stream=_EncodedStream("utf-8"))
        output = reporter._render_rich(DiagnosisReport(total_queries=0, total_time_ms=0.0))

        assert chr(0x2500) in output and chr(0x2502) in output

    def test_cp1252_outputwrapper_destination_renders_ascii(self) -> None:
        """A cp1252 stream wrapped in Django's OutputWrapper renders pure ASCII.

        The real end-to-end pin, on every supported Django (4.2-6.0). Before 5.2
        OutputWrapper subclassed TextIOBase, so its `encoding` resolves to an
        inherited descriptor returning None and its __getattr__ never forwards the
        wrapped stream's cp1252 - so Console(file=wrapper) probes None, falls back
        to utf-8, and emits Unicode box drawing the cp1252 destination cannot
        encode. _probe_target unwraps to the inner stream in that case. This test
        fails on Django <5.2 against the plain Console(file=self._stream) and
        passes on all five versions once the probe target is resolved.
        """
        from django.core.management.base import OutputWrapper

        destination = OutputWrapper(_EncodedStream("cp1252"))
        reporter = ConsoleReporter(stream=destination)
        output = reporter._render_rich(DiagnosisReport(total_queries=0, total_time_ms=0.0))

        # The invariant that matters: the destination can encode what we produced.
        # This is what actually broke - the pre-fix output raised on cp1252.
        output.encode("cp1252")
        # And the box style is ASCII, not merely cp1252-encodable Unicode.
        assert not any(ord(ch) >= 0x2500 for ch in output)  # pure ASCII box
        assert "No issues detected" in output  # positive control: it did render
