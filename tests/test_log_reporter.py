"""Tests for the log reporter.

Verifies that prescriptions are sent to Python's logging module
at appropriate severity levels.
"""

from __future__ import annotations

import logging

from query_doctor.reporters.log_reporter import LogReporter
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


def _make_prescription(
    severity: Severity = Severity.CRITICAL,
    issue_type: IssueType = IssueType.N_PLUS_ONE,
) -> Prescription:
    """Helper to create a Prescription."""
    return Prescription(
        issue_type=issue_type,
        severity=severity,
        description=f"Test {severity.value} issue",
        fix_suggestion="Fix it",
        callsite=CallSite(
            filepath="views.py",
            line_number=10,
            function_name="get_queryset",
        ),
        query_count=5,
    )


def _make_report(
    prescriptions: list[Prescription] | None = None,
) -> DiagnosisReport:
    """Helper to create a DiagnosisReport."""
    return DiagnosisReport(
        prescriptions=prescriptions or [],
        total_queries=10,
        total_time_ms=50.0,
    )


class TestLogReporter:
    """Tests for LogReporter."""

    def test_critical_logged_as_error(self, caplog: logging.LogRecord) -> None:
        """CRITICAL prescriptions should be logged at ERROR level."""
        reporter = LogReporter()
        rx = _make_prescription(severity=Severity.CRITICAL)
        report = _make_report(prescriptions=[rx])
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        assert "Test critical issue" in error_records[0].message

    def test_warning_logged_as_warning(self, caplog: logging.LogRecord) -> None:
        """WARNING prescriptions should be logged at WARNING level."""
        reporter = LogReporter()
        rx = _make_prescription(severity=Severity.WARNING)
        report = _make_report(prescriptions=[rx])
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) >= 1
        assert "Test warning issue" in warn_records[0].message

    def test_info_logged_as_info(self, caplog: logging.LogRecord) -> None:
        """INFO prescriptions should be logged at INFO level."""
        reporter = LogReporter()
        rx = _make_prescription(severity=Severity.INFO)
        report = _make_report(prescriptions=[rx])
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        info_records = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "Test info issue" in r.message
        ]
        assert len(info_records) >= 1

    def test_empty_report_logs_summary(self, caplog: logging.LogRecord) -> None:
        """Empty report should log a summary but no prescriptions."""
        reporter = LogReporter()
        report = _make_report()
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        # Should have logged at least the summary
        assert len(caplog.records) >= 1

    def test_multiple_prescriptions(self, caplog: logging.LogRecord) -> None:
        """Multiple prescriptions should each be logged separately."""
        reporter = LogReporter()
        prescriptions = [
            _make_prescription(severity=Severity.CRITICAL),
            _make_prescription(severity=Severity.WARNING),
            _make_prescription(severity=Severity.INFO),
        ]
        report = _make_report(prescriptions=prescriptions)
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        # At least 3 prescription log entries + summary
        assert len(caplog.records) >= 3

    def test_log_includes_fix_suggestion(self, caplog: logging.LogRecord) -> None:
        """Log messages should include the fix suggestion."""
        reporter = LogReporter()
        rx = _make_prescription(severity=Severity.WARNING)
        report = _make_report(prescriptions=[rx])
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        all_messages = " ".join(r.message for r in caplog.records)
        assert "Fix it" in all_messages

    def test_log_includes_location(self, caplog: logging.LogRecord) -> None:
        """Log messages should include the source location."""
        reporter = LogReporter()
        rx = _make_prescription(severity=Severity.CRITICAL)
        report = _make_report(prescriptions=[rx])
        with caplog.at_level(logging.DEBUG, logger="query_doctor"):
            reporter.report(report)
        all_messages = " ".join(r.message for r in caplog.records)
        assert "views.py:10" in all_messages
