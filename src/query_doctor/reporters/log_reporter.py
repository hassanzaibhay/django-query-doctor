"""Log reporter for sending diagnosis results to Python's logging module.

Maps prescription severity levels to appropriate logging levels:
CRITICAL -> logging.ERROR, WARNING -> logging.WARNING, INFO -> logging.INFO.
"""

from __future__ import annotations

import logging

from query_doctor.types import DiagnosisReport, Prescription, Severity

logger = logging.getLogger("query_doctor")

_SEVERITY_TO_LOG_LEVEL = {
    Severity.CRITICAL: logging.ERROR,
    Severity.WARNING: logging.WARNING,
    Severity.INFO: logging.INFO,
}


class LogReporter:
    """Sends diagnosis reports to Python's logging system.

    Each prescription is logged at the appropriate level based on severity.
    """

    def report(self, report: DiagnosisReport) -> None:
        """Log the diagnosis report.

        Args:
            report: The diagnosis report to log.
        """
        logger.info(
            "Query Doctor: %d queries, %.1fms, %d issues",
            report.total_queries,
            report.total_time_ms,
            report.issues,
        )

        for prescription in report.prescriptions:
            self._log_prescription(prescription)

    def _log_prescription(self, p: Prescription) -> None:
        """Log a single prescription at the appropriate level."""
        level = _SEVERITY_TO_LOG_LEVEL.get(p.severity, logging.INFO)

        location = ""
        if p.callsite:
            location = (
                f" at {p.callsite.filepath}:{p.callsite.line_number} in {p.callsite.function_name}"
            )

        logger.log(
            level,
            "[%s] %s%s | Fix: %s",
            p.severity.value.upper(),
            p.description,
            location,
            p.fix_suggestion,
        )
