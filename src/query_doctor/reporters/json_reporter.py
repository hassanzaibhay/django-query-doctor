"""JSON reporter for structured query diagnosis output.

Produces machine-readable JSON reports suitable for CI/CD pipelines,
monitoring dashboards, and automated processing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from query_doctor.types import DiagnosisReport, Prescription, Severity

logger = logging.getLogger("query_doctor")


class JSONReporter:
    """Formats diagnosis reports as structured JSON.

    Optionally writes the JSON to a file for CI/CD integration.
    """

    def __init__(self, output_path: str | None = None) -> None:
        """Initialize the JSON reporter.

        Args:
            output_path: Optional file path to write JSON output.
                         If None, output is only available via render().
        """
        self._output_path = output_path

    def render(self, report: DiagnosisReport) -> str:
        """Render a diagnosis report as a JSON string.

        Args:
            report: The diagnosis report to render.

        Returns:
            JSON string representation of the report.
        """
        data = self._build_json(report)
        return json.dumps(data, indent=2, default=str)

    def report(self, report: DiagnosisReport) -> None:
        """Write the diagnosis report to the configured output path.

        Args:
            report: The diagnosis report to output.
        """
        output = self.render(report)

        if self._output_path:
            try:
                with open(self._output_path, "w", encoding="utf-8") as f:
                    f.write(output)
            except OSError:
                logger.warning(
                    "query_doctor: failed to write JSON report to %s",
                    self._output_path,
                    exc_info=True,
                )

    def _build_json(self, report: DiagnosisReport) -> dict[str, Any]:
        """Build the JSON-serializable dict from a report."""
        prescriptions_data = [self._prescription_to_dict(p) for p in report.prescriptions]

        critical = sum(1 for p in report.prescriptions if p.severity == Severity.CRITICAL)
        warnings = sum(1 for p in report.prescriptions if p.severity == Severity.WARNING)
        info = sum(1 for p in report.prescriptions if p.severity == Severity.INFO)

        return {
            "version": self._get_version(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_queries": report.total_queries,
                "total_time_ms": report.total_time_ms,
                "issues_found": report.issues,
                "critical": critical,
                "warnings": warnings,
                "info": info,
            },
            "prescriptions": prescriptions_data,
        }

    def _prescription_to_dict(self, p: Prescription) -> dict[str, Any]:
        """Convert a Prescription to a JSON-serializable dict."""
        location = None
        if p.callsite:
            location = {
                "file": p.callsite.filepath,
                "line": p.callsite.line_number,
                "function": p.callsite.function_name,
            }

        return {
            "issue_type": p.issue_type.value,
            "severity": p.severity.value,
            "description": p.description,
            "fix_suggestion": p.fix_suggestion,
            "location": location,
            "query_count": p.query_count,
            "estimated_savings_ms": p.time_saved_ms,
        }

    def _get_version(self) -> str:
        """Get the package version string."""
        try:
            from query_doctor import __version__

            return str(__version__)
        except ImportError:
            return "0.1.0"
