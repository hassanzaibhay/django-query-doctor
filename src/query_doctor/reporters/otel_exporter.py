"""OpenTelemetry exporter for django-query-doctor.

Exports query diagnosis data as OpenTelemetry spans and events for
integration with observability platforms (Datadog, Grafana, Jaeger, etc.).

OpenTelemetry is NOT required. If not installed, the reporter is a no-op.

Configuration:
    QUERY_DOCTOR = {
        "REPORTERS": ["console", "otel"],
    }
"""

from __future__ import annotations

import logging
from typing import Any

from query_doctor.types import DiagnosisReport, Prescription, Severity

logger = logging.getLogger("query_doctor")

try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    trace = None
    StatusCode = None


class OTelReporter:
    """Reports query diagnosis data via OpenTelemetry spans.

    Creates a span for each diagnosis run with attributes for summary
    metrics and events for each prescription. Sets span status to ERROR
    if critical issues are found.

    If OpenTelemetry is not installed, all operations are no-ops.
    """

    def __init__(self, tracer: Any = None) -> None:
        """Initialize the OTel reporter.

        Args:
            tracer: Optional pre-configured OTel tracer. If None, one is
                    created from the global TracerProvider.
        """
        self._tracer = tracer
        self._has_otel = HAS_OTEL or tracer is not None

    @property
    def has_otel(self) -> bool:
        """Whether OpenTelemetry is available."""
        return self._has_otel

    def report(self, report: DiagnosisReport) -> None:
        """Export diagnosis report as OTel span data.

        Args:
            report: The diagnosis report to export.
        """
        if not self._has_otel:
            return

        try:
            self._export(report)
        except Exception:
            logger.warning(
                "query_doctor: OpenTelemetry export failed",
                exc_info=True,
            )

    def _export(self, report: DiagnosisReport) -> None:
        """Export the report using the OTel tracer."""
        tracer = self._get_tracer()

        with tracer.start_span("query_doctor.diagnosis") as span:
            # Set summary attributes
            span.set_attribute("query_doctor.total_queries", report.total_queries)
            span.set_attribute("query_doctor.total_time_ms", report.total_time_ms)
            span.set_attribute("query_doctor.issues_found", report.issues)

            # Add prescription events
            for p in report.prescriptions:
                self._add_prescription_event(span, p)

            # Set status based on severity
            has_critical = any(p.severity == Severity.CRITICAL for p in report.prescriptions)
            if has_critical:
                self._set_error_status(span, "Critical query issues detected")
            else:
                self._set_ok_status(span)

    def _get_tracer(self) -> Any:
        """Get the OTel tracer instance."""
        if self._tracer is not None:
            return self._tracer

        if HAS_OTEL and trace is not None:
            return trace.get_tracer("query_doctor")

        raise RuntimeError("No tracer available")

    def _add_prescription_event(self, span: Any, p: Prescription) -> None:
        """Add a prescription as a span event."""
        attributes: dict[str, Any] = {
            "issue_type": p.issue_type.value,
            "severity": p.severity.value,
            "description": p.description,
            "fix_suggestion": p.fix_suggestion,
            "query_count": p.query_count,
            "time_saved_ms": p.time_saved_ms,
        }

        if p.callsite:
            attributes["location"] = f"{p.callsite.filepath}:{p.callsite.line_number}"

        span.add_event(p.description, attributes=attributes)

    def _set_error_status(self, span: Any, message: str) -> None:
        """Set span status to ERROR."""
        if HAS_OTEL and StatusCode is not None:
            span.set_status(StatusCode.ERROR, message)
        else:
            span.set_status("ERROR", message)

    def _set_ok_status(self, span: Any) -> None:
        """Set span status to OK."""
        if HAS_OTEL and StatusCode is not None:
            span.set_status(StatusCode.OK)
        else:
            span.set_status("OK")
