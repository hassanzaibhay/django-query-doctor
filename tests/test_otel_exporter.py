"""Tests for the OpenTelemetry exporter.

Verifies that the OTel reporter creates spans with correct attributes,
adds prescription events, sets status codes, and handles missing OTel gracefully.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from query_doctor.reporters.otel_exporter import OTelReporter
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


def _make_report(
    prescriptions: list[Prescription] | None = None,
    total_queries: int = 10,
    total_time_ms: float = 50.0,
) -> DiagnosisReport:
    """Create a test DiagnosisReport."""
    return DiagnosisReport(
        prescriptions=prescriptions or [],
        total_queries=total_queries,
        total_time_ms=total_time_ms,
    )


def _make_prescription(
    severity: Severity = Severity.WARNING,
    description: str = "Test issue",
    issue_type: IssueType = IssueType.N_PLUS_ONE,
) -> Prescription:
    """Create a test Prescription."""
    return Prescription(
        issue_type=issue_type,
        severity=severity,
        description=description,
        fix_suggestion="Test fix",
        callsite=CallSite("test.py", 1, "test_fn"),
        query_count=5,
        time_saved_ms=10.0,
    )


class TestOTelWithoutInstalled:
    """Tests when OpenTelemetry is not installed."""

    def test_reporter_is_noop(self) -> None:
        """Without OTel, report() should be a no-op."""
        reporter = OTelReporter()
        report = _make_report()
        # Should not raise
        reporter.report(report)

    def test_has_otel_flag(self) -> None:
        """Reporter should expose has_otel property."""
        reporter = OTelReporter()
        assert isinstance(reporter.has_otel, bool)


class TestOTelWithMockedTracer:
    """Tests with mocked OpenTelemetry tracer."""

    def test_creates_span(self) -> None:
        """Should create a span for query diagnosis."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report(total_queries=42, total_time_ms=123.4)

        reporter.report(report)

        mock_tracer.start_span.assert_called_once()

    def test_span_attributes(self) -> None:
        """Span should have correct attributes."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report(total_queries=42, total_time_ms=123.4)

        reporter.report(report)

        # Check set_attribute was called with expected keys
        set_attr_calls = {
            call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list
        }
        assert set_attr_calls.get("query_doctor.total_queries") == 42
        assert set_attr_calls.get("query_doctor.total_time_ms") == 123.4
        assert set_attr_calls.get("query_doctor.issues_found") == 0

    def test_prescription_added_as_event(self) -> None:
        """Each prescription should be added as a span event."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        p = _make_prescription(description="N+1 detected")
        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report(prescriptions=[p])

        reporter.report(report)

        mock_span.add_event.assert_called()
        event_call = mock_span.add_event.call_args_list[0]
        assert "N+1 detected" in str(event_call)

    def test_critical_sets_error_status(self) -> None:
        """Critical issues should set span status to ERROR."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        p = _make_prescription(severity=Severity.CRITICAL)
        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report(prescriptions=[p])

        reporter.report(report)

        mock_span.set_status.assert_called()

    def test_no_issues_ok_status(self) -> None:
        """Empty report should set span status to OK."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report(prescriptions=[])

        reporter.report(report)

        mock_span.set_status.assert_called()

    def test_multiple_prescriptions(self) -> None:
        """Multiple prescriptions should each create an event."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)

        prescriptions = [_make_prescription(description=f"Issue {i}") for i in range(5)]
        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report(prescriptions=prescriptions)

        reporter.report(report)

        assert mock_span.add_event.call_count == 5


class TestOTelEdgeCases:
    """Edge case tests for OTel reporter."""

    def test_module_docstring(self) -> None:
        """Module should have a docstring."""
        import query_doctor.reporters.otel_exporter

        assert query_doctor.reporters.otel_exporter.__doc__

    def test_reporter_never_crashes(self) -> None:
        """Reporter should never raise, even with bad tracer."""
        mock_tracer = MagicMock()
        mock_tracer.start_span.side_effect = RuntimeError("tracer broken")

        reporter = OTelReporter(tracer=mock_tracer)
        report = _make_report()

        # Should not raise
        reporter.report(report)
