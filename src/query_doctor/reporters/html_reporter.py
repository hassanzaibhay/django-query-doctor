"""HTML reporter for standalone query diagnosis reports.

Generates a self-contained HTML file with inline CSS, summary statistics,
and a sortable list of prescriptions with severity-based styling.
"""

from __future__ import annotations

import html
import logging

from query_doctor.types import DiagnosisReport, Prescription, Severity

logger = logging.getLogger("query_doctor")

_SEVERITY_COLORS = {
    Severity.CRITICAL: "#dc3545",
    Severity.WARNING: "#ffc107",
    Severity.INFO: "#17a2b8",
}

_SEVERITY_LABELS = {
    Severity.CRITICAL: "CRITICAL",
    Severity.WARNING: "WARNING",
    Severity.INFO: "INFO",
}


class HTMLReporter:
    """Generates standalone HTML reports for query diagnosis.

    Produces a single HTML file with inline CSS suitable for
    saving, sharing, or viewing in a browser.
    """

    def __init__(self, output_path: str | None = None) -> None:
        """Initialize the HTML reporter.

        Args:
            output_path: Optional file path to write HTML output.
        """
        self._output_path = output_path

    def render(self, report: DiagnosisReport) -> str:
        """Render a diagnosis report as a standalone HTML string.

        Args:
            report: The diagnosis report to render.

        Returns:
            Complete HTML document as a string.
        """
        return self._build_html(report)

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
                    "query_doctor: failed to write HTML report to %s",
                    self._output_path,
                    exc_info=True,
                )

    def _build_html(self, report: DiagnosisReport) -> str:
        """Build the complete HTML document."""
        critical = sum(1 for p in report.prescriptions if p.severity == Severity.CRITICAL)
        warnings = sum(1 for p in report.prescriptions if p.severity == Severity.WARNING)
        info = sum(1 for p in report.prescriptions if p.severity == Severity.INFO)

        prescriptions_html = self._render_prescriptions(report.prescriptions)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Query Doctor Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f5f5f5; color: #333; padding: 20px; }}
.container {{ max-width: 900px; margin: 0 auto; }}
h1 {{ color: #2c3e50; margin-bottom: 20px; }}
.summary {{ background: #fff; border-radius: 8px; padding: 20px;
            margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.summary h2 {{ margin-bottom: 12px; color: #2c3e50; }}
.stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
.stat {{ text-align: center; min-width: 100px; }}
.stat-value {{ font-size: 28px; font-weight: bold; }}
.stat-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
.stat-critical .stat-value {{ color: #dc3545; }}
.stat-warning .stat-value {{ color: #ffc107; }}
.stat-info .stat-value {{ color: #17a2b8; }}
.prescription {{ background: #fff; border-radius: 8px; padding: 16px;
                 margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                 border-left: 4px solid #ccc; }}
.prescription.critical {{ border-left-color: #dc3545; }}
.prescription.warning {{ border-left-color: #ffc107; }}
.prescription.info {{ border-left-color: #17a2b8; }}
.severity {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
             font-size: 12px; font-weight: bold; color: #fff; }}
.severity.critical {{ background: #dc3545; }}
.severity.warning {{ background: #ffc107; color: #333; }}
.severity.info {{ background: #17a2b8; }}
.description {{ margin-top: 8px; font-size: 15px; }}
.location {{ margin-top: 6px; font-size: 13px; color: #666; }}
.code-context {{ margin-top: 4px; font-family: monospace; font-size: 13px;
                 background: #f8f9fa; padding: 4px 8px; border-radius: 4px; }}
.fix {{ margin-top: 8px; padding: 8px 12px; background: #e8f5e9;
        border-radius: 4px; font-size: 14px; }}
.metrics {{ margin-top: 6px; font-size: 13px; color: #666; }}
.no-issues {{ background: #e8f5e9; border-radius: 8px; padding: 20px;
              text-align: center; color: #2e7d32; font-size: 18px; }}
</style>
</head>
<body>
<div class="container">
<h1>Query Doctor Report</h1>
<div class="summary">
<h2>Summary</h2>
<div class="stats">
<div class="stat">
<div class="stat-value">{report.total_queries}</div>
<div class="stat-label">Total Queries</div>
</div>
<div class="stat">
<div class="stat-value">{report.total_time_ms:.1f}ms</div>
<div class="stat-label">Total Time</div>
</div>
<div class="stat">
<div class="stat-value">{report.issues}</div>
<div class="stat-label">Issues Found</div>
</div>
<div class="stat stat-critical">
<div class="stat-value">{critical}</div>
<div class="stat-label">Critical</div>
</div>
<div class="stat stat-warning">
<div class="stat-value">{warnings}</div>
<div class="stat-label">Warnings</div>
</div>
<div class="stat stat-info">
<div class="stat-value">{info}</div>
<div class="stat-label">Info</div>
</div>
</div>
</div>
{prescriptions_html}
</div>
</body>
</html>"""

    def _render_prescriptions(self, prescriptions: list[Prescription]) -> str:
        """Render the prescriptions section."""
        if not prescriptions:
            return '<div class="no-issues">No issues detected.</div>'

        parts: list[str] = []
        for p in prescriptions:
            parts.append(self._render_one_prescription(p))
        return "\n".join(parts)

    def _render_one_prescription(self, p: Prescription) -> str:
        """Render a single prescription as HTML."""
        severity_class = p.severity.value
        severity_label = _SEVERITY_LABELS.get(p.severity, "INFO")
        desc = html.escape(p.description)
        fix = html.escape(p.fix_suggestion)

        location_html = ""
        if p.callsite:
            cs = p.callsite
            loc = html.escape(f"{cs.filepath}:{cs.line_number} in {cs.function_name}")
            location_html = f'<div class="location">Location: {loc}</div>'
            if cs.code_context:
                code = html.escape(cs.code_context)
                location_html += f'<div class="code-context">{code}</div>'

        metrics_html = ""
        if p.query_count > 0:
            metrics_html = (
                f'<div class="metrics">'
                f"Queries: {p.query_count} | "
                f"Est. savings: ~{p.time_saved_ms:.1f}ms"
                f"</div>"
            )

        return f"""<div class="prescription {severity_class}">
<span class="severity {severity_class}">{severity_label}</span>
<div class="description">{desc}</div>
{location_html}
<div class="fix">Fix: {fix}</div>
{metrics_html}
</div>"""
