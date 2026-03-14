"""Project-wide HTML and JSON report generators.

Generates standalone reports for project-wide diagnosis results,
including app scoreboard, per-URL breakdowns, health scores,
and executive summary.
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any

from query_doctor.project_diagnoser import (
    AppDiagnosisResult,
    ProjectDiagnosisResult,
    URLDiagnosisResult,
)
from query_doctor.types import Severity

logger = logging.getLogger("query_doctor")


def _health_color(score: float) -> str:
    """Return CSS color for a health score.

    Args:
        score: Health score 0-100.

    Returns:
        CSS color string.
    """
    if score >= 80:
        return "#2e7d32"
    if score >= 60:
        return "#f57f17"
    return "#c62828"


def _severity_color(severity: Severity) -> str:
    """Return CSS color for a severity level.

    Args:
        severity: Issue severity.

    Returns:
        CSS color string.
    """
    if severity == Severity.CRITICAL:
        return "#dc3545"
    if severity == Severity.WARNING:
        return "#ff9800"
    return "#2196f3"


class ProjectReportGenerator:
    """Generate standalone HTML reports for project-wide diagnosis.

    Produces a single HTML file with inline CSS/JS, no external deps.
    """

    def generate(self, result: ProjectDiagnosisResult) -> str:
        """Generate the complete HTML report.

        Args:
            result: The project diagnosis result.

        Returns:
            Complete HTML document as a string.
        """
        total_critical = sum(a.critical_count for a in result.app_results)
        total_warnings = sum(a.warning_count for a in result.app_results)
        total_info = result.total_issues - total_critical - total_warnings

        apps_html = self._render_app_scoreboard(result.app_results)
        details_html = self._render_app_details(result.app_results)
        skipped_html = self._render_skipped(result.skipped_urls)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Query Doctor — Project Health Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
       background: #f8f9fa; color: #212529; line-height: 1.5; padding: 24px; }}
.container {{ max-width: 1000px; margin: 0 auto; }}
h1 {{ color: #1a237e; font-size: 24px; margin-bottom: 4px; }}
.subtitle {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
.summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
.card {{ background: #fff; border-radius: 8px; padding: 16px 20px; min-width: 140px;
         box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }}
.card-value {{ font-size: 28px; font-weight: 700; }}
.card-label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
.card-critical .card-value {{ color: #dc3545; }}
.card-warning .card-value {{ color: #ff9800; }}
.card-info .card-value {{ color: #2196f3; }}
.section {{ background: #fff; border-radius: 8px; margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; }}
.section-header {{ padding: 16px 20px; cursor: pointer; display: flex;
                   justify-content: space-between; align-items: center;
                   border-bottom: 1px solid #eee; }}
.section-header:hover {{ background: #f8f9fa; }}
.section-header h2 {{ font-size: 16px; margin: 0; }}
.section-body {{ padding: 16px 20px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 8px 12px; border-bottom: 2px solid #dee2e6;
      font-size: 13px; color: #666; text-transform: uppercase; letter-spacing: 0.5px;
      cursor: pointer; user-select: none; }}
th:hover {{ color: #333; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 14px; }}
.health {{ font-weight: 700; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
          font-size: 11px; font-weight: 600; color: #fff; }}
.badge-critical {{ background: #dc3545; }}
.badge-warning {{ background: #ff9800; }}
.badge-info {{ background: #2196f3; }}
.url-item {{ margin-bottom: 12px; padding: 12px; background: #f8f9fa;
             border-radius: 6px; border-left: 3px solid #dee2e6; }}
.url-path {{ font-family: monospace; font-size: 14px; font-weight: 600; }}
.url-meta {{ font-size: 12px; color: #666; margin-top: 4px; }}
.rx {{ margin-top: 8px; padding: 8px 12px; background: #fff; border-radius: 4px;
       border-left: 3px solid #ccc; }}
.rx-critical {{ border-left-color: #dc3545; }}
.rx-warning {{ border-left-color: #ff9800; }}
.rx-info {{ border-left-color: #2196f3; }}
.rx-desc {{ font-size: 13px; }}
.rx-fix {{ font-size: 12px; color: #2e7d32; margin-top: 4px; }}
.rx-loc {{ font-size: 11px; color: #888; margin-top: 2px; font-family: monospace; }}
.skipped {{ font-size: 13px; color: #666; }}
.skipped code {{ background: #eee; padding: 1px 4px; border-radius: 3px; }}
.empty {{ padding: 24px; text-align: center; color: #666; }}
.collapsible {{ display: none; }}
.collapsible.open {{ display: block; }}
.toggle {{ font-size: 14px; color: #999; transition: transform 0.2s; }}
@media print {{
  .section-header {{ cursor: default; }}
  .collapsible {{ display: block !important; }}
}}
@media (prefers-color-scheme: dark) {{
  body {{ background: #1a1a2e; color: #e0e0e0; }}
  .card, .section {{ background: #16213e; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }}
  .section-header {{ border-bottom-color: #333; }}
  .section-header:hover {{ background: #1a1a2e; }}
  th {{ color: #aaa; border-bottom-color: #444; }}
  td {{ border-bottom-color: #333; }}
  .url-item {{ background: #1a1a2e; border-left-color: #444; }}
  .rx {{ background: #16213e; }}
  h1 {{ color: #82b1ff; }}
  .subtitle {{ color: #aaa; }}
  .card-label {{ color: #aaa; }}
  .skipped code {{ background: #333; }}
}}
</style>
</head>
<body>
<div class="container">
<h1>Query Doctor — Project Health Report</h1>
<div class="subtitle">Generated: {html.escape(result.started_at or "")} |
URLs Analyzed: {result.total_urls_analyzed} |
Overall Health: {result.overall_health_score:.0f}/100</div>

<div class="summary">
<div class="card">
  <div class="card-value">{result.total_urls_analyzed}</div>
  <div class="card-label">URLs Analyzed</div>
</div>
<div class="card">
  <div class="card-value">{len(result.app_results)}</div>
  <div class="card-label">Apps</div>
</div>
<div class="card">
  <div class="card-value">{result.total_queries}</div>
  <div class="card-label">Total Queries</div>
</div>
<div class="card">
  <div class="card-value">{result.total_issues}</div>
  <div class="card-label">Issues Found</div>
</div>
<div class="card card-critical">
  <div class="card-value">{total_critical}</div>
  <div class="card-label">Critical</div>
</div>
<div class="card card-warning">
  <div class="card-value">{total_warnings}</div>
  <div class="card-label">Warnings</div>
</div>
<div class="card card-info">
  <div class="card-value">{total_info}</div>
  <div class="card-label">Info</div>
</div>
</div>

<div class="section">
<div class="section-header" onclick="toggleSection('summary')">
  <h2>Executive Summary</h2>
  <span class="toggle" id="toggle-summary">&#9660;</span>
</div>
<div class="section-body collapsible open" id="section-summary">
{self._render_executive_summary(result, total_critical, total_warnings)}
</div>
</div>

{apps_html}
{details_html}
{skipped_html}

</div>
<script>
function toggleSection(id) {{
  var el = document.getElementById('section-' + id);
  el.classList.toggle('open');
}}
function sortTable(tableId, col) {{
  var table = document.getElementById(tableId);
  if (!table) return;
  var tbody = table.querySelector('tbody');
  var rows = Array.from(tbody.querySelectorAll('tr'));
  var asc = table.dataset.sortCol === String(col) && table.dataset.sortDir === 'asc';
  table.dataset.sortCol = String(col);
  table.dataset.sortDir = asc ? 'desc' : 'asc';
  rows.sort(function(a, b) {{
    var av = a.children[col].dataset.val || a.children[col].textContent;
    var bv = b.children[col].dataset.val || b.children[col].textContent;
    var an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? bn - an : an - bn;
    return asc ? bv.localeCompare(av) : av.localeCompare(bv);
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
}}
</script>
</body>
</html>"""

    def _render_executive_summary(
        self,
        result: ProjectDiagnosisResult,
        total_critical: int,
        total_warnings: int,
    ) -> str:
        """Render the executive summary section."""
        if not result.app_results:
            return '<div class="empty">No URLs were analyzed.</div>'

        worst = min(result.app_results, key=lambda a: a.health_score)
        best = max(result.app_results, key=lambda a: a.health_score)

        lines = [
            f"<p><strong>{len(result.app_results)}</strong> apps, "
            f"<strong>{result.total_urls_analyzed}</strong> URLs, "
            f"<strong>{result.total_issues}</strong> issues found.</p>",
        ]

        if total_critical > 0:
            lines.append(
                f'<p style="color:#dc3545"><strong>{total_critical} critical</strong> '
                f"issues require immediate attention.</p>"
            )

        if len(result.app_results) > 1:
            lines.append(
                f"<p>Top offender: <strong>{html.escape(worst.app_name)}</strong> "
                f"(health: {worst.health_score:.0f}/100). "
                f"Healthiest: <strong>{html.escape(best.app_name)}</strong> "
                f"(health: {best.health_score:.0f}/100).</p>"
            )

        if result.skipped_urls:
            lines.append(f"<p>{len(result.skipped_urls)} URLs were skipped.</p>")

        return "\n".join(lines)

    def _render_app_scoreboard(self, apps: list[AppDiagnosisResult]) -> str:
        """Render the sortable app scoreboard table."""
        if not apps:
            return ""

        rows = []
        for app in sorted(apps, key=lambda a: a.health_score):
            color = _health_color(app.health_score)
            rows.append(
                f"<tr>"
                f"<td>{html.escape(app.app_name)}</td>"
                f'<td class="health" style="color:{color}" '
                f'data-val="{app.health_score:.0f}">{app.health_score:.0f}/100</td>'
                f'<td data-val="{app.total_queries}">{app.total_queries}</td>'
                f'<td data-val="{app.total_issues}">{app.total_issues}</td>'
                f'<td data-val="{app.critical_count}">{app.critical_count}</td>'
                f'<td data-val="{app.warning_count}">{app.warning_count}</td>'
                f"</tr>"
            )

        return f"""<div class="section">
<div class="section-header" onclick="toggleSection('scoreboard')">
  <h2>App Scoreboard</h2>
  <span class="toggle" id="toggle-scoreboard">&#9660;</span>
</div>
<div class="section-body collapsible open" id="section-scoreboard">
<table id="scoreboard-table">
<thead><tr>
<th onclick="sortTable('scoreboard-table',0)">App</th>
<th onclick="sortTable('scoreboard-table',1)">Health</th>
<th onclick="sortTable('scoreboard-table',2)">Queries</th>
<th onclick="sortTable('scoreboard-table',3)">Issues</th>
<th onclick="sortTable('scoreboard-table',4)">Critical</th>
<th onclick="sortTable('scoreboard-table',5)">Warnings</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
</div>
</div>"""

    def _render_app_details(self, apps: list[AppDiagnosisResult]) -> str:
        """Render per-app detail sections."""
        parts = []
        for app in sorted(apps, key=lambda a: a.health_score):
            app_id = html.escape(app.app_name.replace(".", "-"))
            color = _health_color(app.health_score)
            urls_html = self._render_url_results(app.url_results)

            parts.append(f"""<div class="section">
<div class="section-header" onclick="toggleSection('app-{app_id}')">
  <h2>{html.escape(app.app_name)}
  <span class="health" style="color:{color}">{app.health_score:.0f}/100</span></h2>
  <span class="toggle">&#9660;</span>
</div>
<div class="section-body collapsible" id="section-app-{app_id}">
{urls_html}
</div>
</div>""")

        return "\n".join(parts)

    def _render_url_results(self, url_results: list[URLDiagnosisResult]) -> str:
        """Render per-URL results within an app."""
        parts = []
        for ur in url_results:
            path = html.escape(ur.url.pattern)
            queries = ur.report.total_queries if ur.report else 0
            issues = ur.report.issues if ur.report else 0
            status = ur.status_code or "—"

            if ur.error:
                parts.append(
                    f'<div class="url-item" style="border-left-color:#dc3545">'
                    f'<div class="url-path">{path}</div>'
                    f'<div class="url-meta">Error: {html.escape(ur.error)}</div>'
                    f"</div>"
                )
                continue

            parts.append('<div class="url-item">')
            parts.append(
                f'<div class="url-path">{path}</div>'
                f'<div class="url-meta">'
                f"Status: {status} | Queries: {queries} | "
                f"Issues: {issues} | Time: {ur.duration_ms:.0f}ms</div>"
            )

            if ur.report:
                for p in ur.report.prescriptions:
                    sev_class = p.severity.value
                    badge_class = f"badge-{sev_class}"
                    parts.append(
                        f'<div class="rx rx-{sev_class}">'
                        f'<span class="badge {badge_class}">{p.severity.value.upper()}</span> '
                        f'<span class="rx-desc">{html.escape(p.description)}</span>'
                        f'<div class="rx-fix">Fix: {html.escape(p.fix_suggestion)}</div>'
                    )
                    if p.callsite:
                        parts.append(
                            f'<div class="rx-loc">'
                            f"{html.escape(p.callsite.filepath)}:{p.callsite.line_number}"
                            f"</div>"
                        )
                    parts.append("</div>")

            parts.append("</div>")

        if not parts:
            parts.append('<div class="empty">No URLs in this app.</div>')

        return "\n".join(parts)

    def _render_skipped(self, skipped: list[tuple[str, str]]) -> str:
        """Render the skipped URLs section."""
        if not skipped:
            return ""

        rows = []
        for pattern, reason in skipped:
            rows.append(
                f'<div class="skipped">'
                f"<code>{html.escape(pattern)}</code> — {html.escape(reason)}</div>"
            )

        return f"""<div class="section">
<div class="section-header" onclick="toggleSection('skipped')">
  <h2>Skipped URLs ({len(skipped)})</h2>
  <span class="toggle">&#9660;</span>
</div>
<div class="section-body collapsible" id="section-skipped">
{"".join(rows)}
</div>
</div>"""


class ProjectJsonReporter:
    """Generate JSON reports for project-wide diagnosis results."""

    def generate(self, result: ProjectDiagnosisResult) -> str:
        """Generate the JSON report string.

        Args:
            result: The project diagnosis result.

        Returns:
            JSON string.
        """
        data = self._build(result)
        return json.dumps(data, indent=2, default=str)

    def _build(self, result: ProjectDiagnosisResult) -> dict[str, Any]:
        """Build the JSON-serializable dict."""
        total_critical = sum(a.critical_count for a in result.app_results)
        total_warnings = sum(a.warning_count for a in result.app_results)

        return {
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "summary": {
                "total_urls": result.total_urls_analyzed,
                "total_queries": result.total_queries,
                "total_issues": result.total_issues,
                "critical": total_critical,
                "warnings": total_warnings,
                "health_score": round(result.overall_health_score, 1),
            },
            "apps": [self._app_to_dict(a) for a in result.app_results],
            "skipped_urls": [{"pattern": p, "reason": r} for p, r in result.skipped_urls],
        }

    def _app_to_dict(self, app: AppDiagnosisResult) -> dict[str, Any]:
        """Convert an AppDiagnosisResult to a dict."""
        return {
            "name": app.app_name,
            "health_score": round(app.health_score, 1),
            "total_queries": app.total_queries,
            "total_issues": app.total_issues,
            "critical_count": app.critical_count,
            "warning_count": app.warning_count,
            "urls": [self._url_to_dict(u) for u in app.url_results],
        }

    def _url_to_dict(self, ur: URLDiagnosisResult) -> dict[str, Any]:
        """Convert a URLDiagnosisResult to a dict."""
        prescriptions = []
        if ur.report:
            for p in ur.report.prescriptions:
                rx: dict[str, Any] = {
                    "issue_type": p.issue_type.value,
                    "severity": p.severity.value,
                    "description": p.description,
                    "fix_suggestion": p.fix_suggestion,
                }
                if p.callsite:
                    rx["location"] = f"{p.callsite.filepath}:{p.callsite.line_number}"
                prescriptions.append(rx)

        return {
            "pattern": ur.url.pattern,
            "status_code": ur.status_code,
            "queries": ur.report.total_queries if ur.report else 0,
            "issues": ur.report.issues if ur.report else 0,
            "duration_ms": round(ur.duration_ms, 1),
            "error": ur.error,
            "prescriptions": prescriptions,
        }
