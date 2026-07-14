"""Tests that user-facing output surfaces are pure ASCII.

Non-ASCII punctuation (em/en dashes) in strings that reach a terminal,
a file written by the tool, or argparse help text can break ASCII-locale
CI pipelines and produce mojibake on cp1252 consoles. The worst case is
``fix_queries --apply`` writing an em dash into the user's own source
file. These tests pin every such surface to ASCII.
"""

from __future__ import annotations

from pathlib import Path

from query_doctor.analyzers.complexity import QueryComplexityAnalyzer
from query_doctor.fixer import QueryFixer
from query_doctor.reporters.console import ConsoleReporter
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


def _make_prescription(
    issue_type: IssueType,
    filepath: str,
    line_number: int,
    fix_suggestion: str,
) -> Prescription:
    """Create a Prescription for testing."""
    return Prescription(
        issue_type=issue_type,
        severity=Severity.WARNING,
        description="Test issue",
        fix_suggestion=fix_suggestion,
        callsite=CallSite(
            filepath=filepath,
            line_number=line_number,
            function_name="get_queryset",
        ),
    )


def _make_query(sql: str) -> CapturedQuery:
    """Create a CapturedQuery from raw SQL for testing."""
    return CapturedQuery(
        sql=sql,
        params=None,
        duration_ms=1.0,
        fingerprint="abc123",
        normalized_sql=sql.lower(),
        callsite=CallSite(
            filepath="myapp/views.py",
            line_number=10,
            function_name="get_queryset",
        ),
        is_select=True,
        tables=["books"],
    )


class TestAppliedFixIsAscii:
    """The auto-applied missing_index TODO comment must be pure ASCII."""

    def test_missing_index_todo_comment_is_ascii(self, tmp_path: Path) -> None:
        """fix_queries --apply must never write non-ASCII into user source."""
        source = tmp_path / "models.py"
        source.write_text(
            "from django.db import models\n"
            "\n"
            "class Book(models.Model):\n"
            "    title = models.CharField(max_length=100)\n",
            encoding="utf-8",
        )
        rx = _make_prescription(
            issue_type=IssueType.MISSING_INDEX,
            filepath=str(source),
            line_number=4,
            fix_suggestion="Add db_index=True to the 'title' field",
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 1  # positive control: a fix was produced
        modified = fixer.apply_fixes(fixes, backup=False)
        assert modified == [str(source)]  # positive control: fix was written

        content = source.read_text(encoding="utf-8")
        assert "# TODO" in content  # positive control: comment injected
        content.encode("ascii")  # must not raise UnicodeEncodeError


class TestConsoleOutputIsAscii:
    """Reporter output for real analyzer findings must be ASCII-encodable."""

    def test_complexity_finding_renders_ascii(self) -> None:
        """The complexity analyzer's fix_suggestion reaches console/JSON."""
        analyzer = QueryComplexityAnalyzer()
        sql = (
            "SELECT b.id FROM books b "
            "JOIN authors a ON b.author_id = a.id "
            "JOIN publishers p ON b.publisher_id = p.id "
            "JOIN categories c ON c.book_id = b.id "
            "JOIN tags t ON t.book_id = b.id "
            "WHERE b.id = ?"
        )
        prescriptions = analyzer.analyze([_make_query(sql)])
        assert len(prescriptions) == 1  # positive control: finding produced

        report = DiagnosisReport()
        report.prescriptions = prescriptions
        report.total_queries = 1
        output = ConsoleReporter()._render_plain(report)
        assert prescriptions[0].description in output  # positive control
        output.encode("ascii")  # must not raise UnicodeEncodeError
