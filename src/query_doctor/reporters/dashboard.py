"""HTML benchmark dashboard reporter for QueryTurbo.

Generates a standalone HTML file with embedded Chart.js graphs showing
cache performance metrics. The report is a static snapshot of the
current process's cache state.

The HTML is self-contained: inline CSS, Chart.js loaded from CDN.
No Django template engine dependency — uses Python string formatting.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


class DashboardReporter:
    """Generate standalone HTML benchmark dashboard.

    Creates a professional, dark-mode compatible HTML report with:
    - Cache overview summary cards
    - Top optimized queries table (sortable)
    - Chart.js bar/pie charts
    """

    def generate(
        self,
        stats_snapshot: dict[str, Any],
        output_path: str = "query_doctor_report.html",
    ) -> str:
        """Write HTML report to disk.

        Args:
            stats_snapshot: Statistics dict from TurboStats.snapshot().
            output_path: Path for the output HTML file.

        Returns:
            The output file path.
        """
        html_content = self._render_template(stats_snapshot)
        Path(output_path).write_text(html_content, encoding="utf-8")
        return output_path

    def render_to_string(self, stats_snapshot: dict[str, Any]) -> str:
        """Render the dashboard to an HTML string without writing to disk.

        Args:
            stats_snapshot: Statistics dict from TurboStats.snapshot().

        Returns:
            Complete HTML string.
        """
        return self._render_template(stats_snapshot)

    def _render_template(self, stats: dict[str, Any]) -> str:
        """Build the complete HTML string.

        Uses f-strings for template rendering. Does NOT require Django's
        template engine — works standalone in management commands.

        Args:
            stats: The statistics snapshot dict.

        Returns:
            Complete HTML document string.
        """
        total_hits = stats.get("total_hits", 0)
        total_misses = stats.get("total_misses", 0)
        hit_rate = stats.get("hit_rate", 0)
        cache_size = stats.get("cache_size", 0)
        max_size = stats.get("max_size", 0)
        evictions = stats.get("evictions", 0)
        top_queries = stats.get("top_queries", [])
        prepare_stats = stats.get("prepare_stats", {})

        hit_rate_pct = f"{hit_rate * 100:.1f}"
        utilization_pct = f"{(cache_size / max(1, max_size)) * 100:.1f}"

        prepared_count = prepare_stats.get("prepared_count", 0)
        unprepared_count = prepare_stats.get("unprepared_count", 0)

        # Build table rows
        table_rows = self._build_table_rows(top_queries)

        # Build chart data
        chart_labels = []
        for q in top_queries[:10]:
            preview = q.get("sql_preview", "")
            label = preview[:60] + "..." if len(preview) > 60 else preview
            chart_labels.append(label)
        chart_labels_json = json.dumps(chart_labels)
        chart_hits_json = json.dumps([q.get("hit_count", 0) for q in top_queries[:10]])

        return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QueryTurbo Benchmark Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #1a1b2e;
            --bg-secondary: #252640;
            --bg-card: #2a2b45;
            --text-primary: #e8e8f0;
            --text-secondary: #a0a0b8;
            --accent: #6c7ce8;
            --accent-light: #8b9bf0;
            --success: #4caf88;
            --warning: #f0a040;
            --danger: #e85050;
            --border: #383860;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
        }}
        .header {{
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--border);
        }}
        .header h1 {{
            font-size: 2rem;
            color: var(--accent-light);
            margin-bottom: 0.25rem;
        }}
        .header .subtitle {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1.25rem;
            border: 1px solid var(--border);
        }}
        .card .label {{
            color: var(--text-secondary);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .card .value {{
            font-size: 2rem;
            font-weight: 700;
            margin-top: 0.25rem;
        }}
        .card .value.success {{ color: var(--success); }}
        .card .value.accent {{ color: var(--accent-light); }}
        .card .value.warning {{ color: var(--warning); }}
        .charts {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        .chart-container {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid var(--border);
        }}
        .chart-container h3 {{
            margin-bottom: 1rem;
            color: var(--accent-light);
            font-size: 1rem;
        }}
        .chart-wrap {{
            position: relative;
            height: 300px;
        }}
        .section-title {{
            font-size: 1.25rem;
            color: var(--accent-light);
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--border);
            margin-bottom: 2rem;
        }}
        th {{
            background: var(--bg-secondary);
            padding: 0.75rem 1rem;
            text-align: left;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            cursor: pointer;
            user-select: none;
        }}
        th:hover {{
            color: var(--accent-light);
        }}
        td {{
            padding: 0.75rem 1rem;
            border-top: 1px solid var(--border);
            font-size: 0.9rem;
        }}
        tr:hover td {{
            background: var(--bg-secondary);
        }}
        .sql-preview {{
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            font-size: 0.8rem;
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: var(--accent-light);
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-yes {{ background: rgba(76, 175, 136, 0.2); color: var(--success); }}
        .badge-no {{ background: rgba(160, 160, 184, 0.15); color: var(--text-secondary); }}
        .empty-state {{
            text-align: center;
            padding: 3rem;
            color: var(--text-secondary);
        }}
        .footer {{
            text-align: center;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 0.8rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>QueryTurbo Benchmark Dashboard</h1>
        <p class="subtitle">SQL Cache Performance &mdash; django-query-doctor</p>
    </div>

    <!-- Section 1: Cache Overview -->
    <div class="cards">
        <div class="card">
            <div class="label">Cache Hits</div>
            <div class="value success">{total_hits:,}</div>
        </div>
        <div class="card">
            <div class="label">Cache Misses</div>
            <div class="value warning">{total_misses:,}</div>
        </div>
        <div class="card">
            <div class="label">Hit Rate</div>
            <div class="value accent">{hit_rate_pct}%</div>
        </div>
        <div class="card">
            <div class="label">Cache Utilization</div>
            <div class="value accent">{cache_size} / {max_size} ({utilization_pct}%)</div>
        </div>
        <div class="card">
            <div class="label">Evictions</div>
            <div class="value">{evictions:,}</div>
        </div>
    </div>

    <!-- Section 3: Charts -->
    <div class="charts">
        <div class="chart-container">
            <h3>Cache Hits vs Misses</h3>
            <div class="chart-wrap">
                <canvas id="hitMissChart"></canvas>
            </div>
        </div>
        <div class="chart-container">
            <h3>Top Queries by Hit Count</h3>
            <div class="chart-wrap">
                <canvas id="topQueriesChart"></canvas>
            </div>
        </div>
        {self._render_prepare_chart_container(prepared_count, unprepared_count)}
    </div>

    <!-- Section 2: Top Optimized Queries -->
    <h2 class="section-title">Top Optimized Queries</h2>
    {self._render_table_or_empty(table_rows)}

    <div class="footer">
        Generated by django-query-doctor &mdash; QueryTurbo Benchmark Dashboard<br>
        Data reflects the current process cache. Cache resets on server restart.
    </div>

    <script>
    // Chart.js configuration
    const chartColors = {{
        accent: '#6c7ce8',
        accentLight: '#8b9bf0',
        success: '#4caf88',
        warning: '#f0a040',
        danger: '#e85050',
        textSecondary: '#a0a0b8',
    }};

    Chart.defaults.color = chartColors.textSecondary;
    Chart.defaults.borderColor = 'rgba(56, 56, 96, 0.5)';

    // Hit vs Miss Pie Chart
    new Chart(document.getElementById('hitMissChart'), {{
        type: 'doughnut',
        data: {{
            labels: ['Hits', 'Misses'],
            datasets: [{{
                data: [{total_hits}, {total_misses}],
                backgroundColor: [chartColors.success, chartColors.warning],
                borderWidth: 0,
            }}],
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ position: 'bottom' }},
            }},
        }},
    }});

    // Top Queries Bar Chart
    new Chart(document.getElementById('topQueriesChart'), {{
        type: 'bar',
        data: {{
            labels: {chart_labels_json},
            datasets: [{{
                label: 'Hit Count',
                data: {chart_hits_json},
                backgroundColor: chartColors.accent,
                borderRadius: 4,
            }}],
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {{
                legend: {{ display: false }},
            }},
            scales: {{
                x: {{ grid: {{ color: 'rgba(56, 56, 96, 0.3)' }} }},
                y: {{
                    grid: {{ display: false }},
                    ticks: {{ font: {{ size: 10 }} }},
                }},
            }},
        }},
    }});

    {self._render_prepare_chart_js(prepared_count, unprepared_count)}

    // Simple table sorting
    document.querySelectorAll('th[data-sort]').forEach(th => {{
        th.addEventListener('click', () => {{
            const table = th.closest('table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const idx = Array.from(th.parentElement.children).indexOf(th);
            const isNumeric = th.dataset.sort === 'number';
            const currentDir = th.dataset.dir === 'asc' ? 'desc' : 'asc';

            // Reset all headers
            th.parentElement.querySelectorAll('th').forEach(h => h.dataset.dir = '');
            th.dataset.dir = currentDir;

            rows.sort((a, b) => {{
                let aVal = a.children[idx].textContent.trim();
                let bVal = b.children[idx].textContent.trim();
                if (isNumeric) {{
                    aVal = parseFloat(aVal.replace(/,/g, '')) || 0;
                    bVal = parseFloat(bVal.replace(/,/g, '')) || 0;
                }}
                if (currentDir === 'asc') return aVal > bVal ? 1 : -1;
                return aVal < bVal ? 1 : -1;
            }});

            rows.forEach(row => tbody.appendChild(row));
        }});
    }});
    </script>
</body>
</html>"""

    def _build_table_rows(self, top_queries: list[dict[str, Any]]) -> str:
        """Build HTML table rows for top queries.

        Args:
            top_queries: List of query info dicts.

        Returns:
            HTML string of <tr> elements.
        """
        rows: list[str] = []
        for i, q in enumerate(top_queries, 1):
            sql_preview = html.escape(q.get("sql_preview", ""))
            hit_count = q.get("hit_count", 0)
            model = html.escape(q.get("model", "-"))
            is_prepared = q.get("is_prepared", False)
            prepared_badge = (
                '<span class="badge badge-yes">Yes</span>'
                if is_prepared
                else '<span class="badge badge-no">No</span>'
            )

            rows.append(f"""        <tr>
            <td>{i}</td>
            <td class="sql-preview" title="{sql_preview}">{sql_preview}</td>
            <td>{model}</td>
            <td>{hit_count:,}</td>
            <td>{prepared_badge}</td>
        </tr>""")

        return "\n".join(rows)

    def _render_table_or_empty(self, table_rows: str) -> str:
        """Render either the queries table or an empty state message.

        Args:
            table_rows: Pre-rendered HTML table rows.

        Returns:
            HTML string.
        """
        if not table_rows.strip():
            return (
                '<div class="empty-state">'
                "No cached queries yet. The cache populates "
                "as queries are executed."
                "</div>"
            )

        return f"""<table>
        <thead>
            <tr>
                <th data-sort="number">#</th>
                <th data-sort="string">SQL Preview</th>
                <th data-sort="string">Model</th>
                <th data-sort="number">Hit Count</th>
                <th data-sort="string">Prepared</th>
            </tr>
        </thead>
        <tbody>
{table_rows}
        </tbody>
    </table>"""

    def _render_prepare_chart_container(self, prepared: int, unprepared: int) -> str:
        """Render the prepare chart container if applicable.

        Args:
            prepared: Count of prepared queries.
            unprepared: Count of unprepared queries.

        Returns:
            HTML string for the chart container, or empty string.
        """
        if prepared + unprepared == 0:
            return ""

        return """<div class="chart-container">
            <h3>Prepared vs Non-Prepared Queries</h3>
            <div class="chart-wrap">
                <canvas id="prepareChart"></canvas>
            </div>
        </div>"""

    def _render_prepare_chart_js(self, prepared: int, unprepared: int) -> str:
        """Render the JavaScript for the prepare chart.

        Args:
            prepared: Count of prepared queries.
            unprepared: Count of unprepared queries.

        Returns:
            JavaScript string for the chart, or empty string.
        """
        if prepared + unprepared == 0:
            return ""

        return f"""
    // Prepared vs Non-Prepared Chart
    new Chart(document.getElementById('prepareChart'), {{
        type: 'bar',
        data: {{
            labels: ['Prepared', 'Non-Prepared'],
            datasets: [{{
                data: [{prepared}, {unprepared}],
                backgroundColor: [chartColors.accent, chartColors.textSecondary],
                borderRadius: 4,
            }}],
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ display: false }},
            }},
            scales: {{
                y: {{ beginAtZero: true }},
            }},
        }},
    }});"""
