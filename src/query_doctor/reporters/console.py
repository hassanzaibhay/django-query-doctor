"""Console reporter for query diagnosis results.

Formats DiagnosisReport output for terminal display. Uses Rich library
for beautiful formatting if available, falls back to plain text otherwise.
"""

from __future__ import annotations

import sys
from typing import Any

from query_doctor.types import DiagnosisReport, Prescription, Severity

_SEVERITY_ICONS = {
    Severity.CRITICAL: "CRITICAL",
    Severity.WARNING: "WARNING",
    Severity.INFO: "INFO",
}


class ConsoleReporter:
    """Formats and prints diagnosis reports to the console.

    Uses Rich for styled output if available, otherwise plain text.
    """

    def __init__(self, stream: Any = None) -> None:
        """Initialize the console reporter.

        Args:
            stream: Output stream (file-like object). Defaults to sys.stderr.
                    Accepts TextIO, Django's OutputWrapper, or any writable stream.
        """
        self._stream = stream or sys.stderr

    def render(self, report: DiagnosisReport) -> str:
        """Render a diagnosis report as a formatted string.

        Args:
            report: The diagnosis report to render.

        Returns:
            Formatted string representation of the report.
        """
        try:
            return self._render_rich(report)
        except ImportError:
            return self._render_plain(report)

    def report(self, report: DiagnosisReport) -> None:
        """Print the diagnosis report to the configured stream.

        Args:
            report: The diagnosis report to print.
        """
        output = self.render(report)
        print(output, file=self._stream)

    def _render_rich(self, report: DiagnosisReport) -> str:
        """Render with Rich formatting."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text

        console = Console(file=None, force_terminal=False)
        parts: list[str] = []

        # Header
        header = (
            f"Query Doctor Report | "
            f"Total queries: {report.total_queries} | "
            f"Time: {report.total_time_ms:.1f}ms | "
            f"Issues: {report.issues}"
        )

        with console.capture() as capture:
            console.print(Panel(header, title="Query Doctor", border_style="blue"))

            for prescription in report.prescriptions:
                self._render_rich_prescription(console, prescription)

            if report.issues == 0:
                console.print(Text("No issues detected.", style="green"))

        parts.append(capture.get())
        return "".join(parts)

    def _render_rich_prescription(self, console: object, prescription: Prescription) -> None:
        """Render a single prescription with Rich."""
        from rich.console import Console as RichConsole

        assert isinstance(console, RichConsole)

        severity_label = _SEVERITY_ICONS.get(prescription.severity, "INFO")
        style = "red bold" if prescription.severity == Severity.CRITICAL else "yellow bold"

        console.print()
        console.print(f"[{style}]{severity_label}[/{style}]: {prescription.description}")

        if prescription.callsite:
            cs = prescription.callsite
            console.print(f"   Location: {cs.filepath}:{cs.line_number} in {cs.function_name}")
            if cs.code_context:
                console.print(f"   Code: {cs.code_context}")

        console.print(f"   Fix: {prescription.fix_suggestion}")

        if prescription.query_count > 0:
            console.print(
                f"   Queries: {prescription.query_count} | "
                f"Est. savings: ~{prescription.time_saved_ms:.1f}ms"
            )

    def _render_plain(self, report: DiagnosisReport) -> str:
        """Render as plain text (fallback when Rich is not installed)."""
        lines: list[str] = []

        # Header
        lines.append("=" * 60)
        lines.append("Query Doctor Report")
        lines.append(
            f"Total queries: {report.total_queries} | "
            f"Time: {report.total_time_ms:.1f}ms | "
            f"Issues: {report.issues}"
        )
        lines.append("=" * 60)

        for prescription in report.prescriptions:
            lines.append("")
            severity_label = _SEVERITY_ICONS.get(prescription.severity, "INFO")
            lines.append(f"{severity_label}: {prescription.description}")

            if prescription.callsite:
                cs = prescription.callsite
                lines.append(f"   Location: {cs.filepath}:{cs.line_number} in {cs.function_name}")
                if cs.code_context:
                    lines.append(f"   Code: {cs.code_context}")

            lines.append(f"   Fix: {prescription.fix_suggestion}")

            if prescription.query_count > 0:
                lines.append(
                    f"   Queries: {prescription.query_count} | "
                    f"Est. savings: ~{prescription.time_saved_ms:.1f}ms"
                )

        if report.issues == 0:
            lines.append("")
            lines.append("No issues detected.")

        lines.append("")
        return "\n".join(lines)
