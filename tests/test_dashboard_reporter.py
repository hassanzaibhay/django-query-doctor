"""Tests for the benchmark dashboard HTML reporter.

Validates that the DashboardReporter generates valid HTML with
correct data, handles empty states gracefully, and includes
Chart.js references.
"""

from __future__ import annotations

import os

from query_doctor.reporters.dashboard import DashboardReporter


def _make_stats(
    total_hits: int = 100,
    total_misses: int = 20,
    hit_rate: float = 0.833,
    cache_size: int = 50,
    max_size: int = 1024,
    evictions: int = 0,
    top_queries: list | None = None,
    prepare_stats: dict | None = None,
) -> dict:
    """Create a test statistics snapshot."""
    if top_queries is None:
        top_queries = [
            {
                "sql_preview": 'SELECT "myapp_user"."id" FROM "myapp_user" WHERE ...',
                "hit_count": 50,
                "model": "myapp.User",
                "is_prepared": True,
            },
            {
                "sql_preview": 'SELECT "myapp_book"."id" FROM "myapp_book" WHERE ...',
                "hit_count": 30,
                "model": "myapp.Book",
                "is_prepared": False,
            },
        ]
    if prepare_stats is None:
        prepare_stats = {"prepared_count": 10, "unprepared_count": 40}

    return {
        "timestamp": 1710000000.0,
        "total_hits": total_hits,
        "total_misses": total_misses,
        "hit_rate": hit_rate,
        "cache_size": cache_size,
        "max_size": max_size,
        "evictions": evictions,
        "top_queries": top_queries,
        "prepare_stats": prepare_stats,
    }


class TestDashboardReporter:
    """Tests for DashboardReporter HTML generation."""

    def test_generates_valid_html(self, tmp_path):
        """Report contains proper HTML structure with data."""
        stats = _make_stats()
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_report.html")

        path = reporter.generate(stats, output_path=output_path)

        assert os.path.exists(path)
        with open(path) as f:
            html = f.read()

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "Chart" in html  # Chart.js reference
        assert "83.3" in html  # Hit rate percentage
        assert "myapp.User" in html  # Top query model

    def test_contains_summary_cards(self, tmp_path):
        """Report includes cache overview summary cards."""
        stats = _make_stats(total_hits=500, total_misses=100, evictions=5)
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_cards.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "500" in html  # Total hits
        assert "100" in html  # Total misses
        assert "Cache Hits" in html
        assert "Cache Misses" in html
        assert "Hit Rate" in html
        assert "Evictions" in html

    def test_contains_top_queries_table(self, tmp_path):
        """Report includes the top queries table."""
        stats = _make_stats()
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_table.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "Top Optimized Queries" in html
        assert "SQL Preview" in html
        assert "Hit Count" in html
        assert "myapp_user" in html

    def test_contains_chart_js_cdn(self, tmp_path):
        """Report includes Chart.js CDN link."""
        stats = _make_stats()
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_cdn.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "cdn.jsdelivr.net/npm/chart.js" in html

    def test_contains_charts(self, tmp_path):
        """Report includes chart canvas elements."""
        stats = _make_stats()
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_charts.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "hitMissChart" in html
        assert "topQueriesChart" in html

    def test_prepare_chart_when_stats_present(self, tmp_path):
        """Prepare chart shows when prepare stats are present."""
        stats = _make_stats(
            prepare_stats={"prepared_count": 10, "unprepared_count": 40}
        )
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_prepare.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "prepareChart" in html
        assert "Prepared vs Non-Prepared" in html

    def test_no_prepare_chart_when_zero_stats(self, tmp_path):
        """Prepare chart is omitted when both counts are zero."""
        stats = _make_stats(
            prepare_stats={"prepared_count": 0, "unprepared_count": 0}
        )
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_no_prepare.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "prepareChart" not in html

    def test_sortable_table_js(self, tmp_path):
        """Report includes table sorting JavaScript."""
        stats = _make_stats()
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_sort.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "data-sort" in html
        assert "addEventListener" in html

    def test_html_escaping(self, tmp_path):
        """SQL with special characters is properly escaped."""
        stats = _make_stats(
            top_queries=[
                {
                    "sql_preview": 'SELECT "id" FROM "t" WHERE "x" < 5 & "y" > 3',
                    "hit_count": 10,
                    "model": "test.Model",
                    "is_prepared": False,
                }
            ]
        )
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_escape.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        # Should have escaped & to &amp;
        assert "&amp;" in html

    def test_prepared_badges(self, tmp_path):
        """Prepared status shows as Yes/No badges."""
        stats = _make_stats()
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_badges.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "badge-yes" in html  # First query is prepared
        assert "badge-no" in html  # Second query is not prepared


class TestDashboardReporterEmptyState:
    """Tests for dashboard with empty/zero data."""

    def test_empty_stats(self, tmp_path):
        """Dashboard handles zero data gracefully."""
        stats = {
            "total_hits": 0,
            "total_misses": 0,
            "hit_rate": 0,
            "cache_size": 0,
            "max_size": 1024,
            "evictions": 0,
            "top_queries": [],
            "prepare_stats": {"prepared_count": 0, "unprepared_count": 0},
        }
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_empty.html")

        path = reporter.generate(stats, output_path=output_path)
        assert os.path.exists(path)

        with open(path) as f:
            html = f.read()

        assert "<html" in html
        assert "No cached queries" in html  # Empty state message

    def test_no_top_queries_shows_empty_state(self, tmp_path):
        """When no queries are cached, show empty state instead of table."""
        stats = _make_stats(top_queries=[])
        reporter = DashboardReporter()
        output_path = str(tmp_path / "test_no_queries.html")

        reporter.generate(stats, output_path=output_path)
        with open(output_path) as f:
            html = f.read()

        assert "No cached queries" in html


class TestDashboardReporterRenderToString:
    """Tests for render_to_string method."""

    def test_render_to_string_returns_html(self):
        """render_to_string returns complete HTML without writing to disk."""
        stats = _make_stats()
        reporter = DashboardReporter()

        html = reporter.render_to_string(stats)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "QueryTurbo" in html

    def test_render_to_string_matches_generate(self, tmp_path):
        """render_to_string output matches generate output."""
        stats = _make_stats()
        reporter = DashboardReporter()

        html_string = reporter.render_to_string(stats)
        output_path = str(tmp_path / "test_match.html")
        reporter.generate(stats, output_path=output_path)

        with open(output_path) as f:
            html_file = f.read()

        assert html_string == html_file


class TestDashboardManagementCommand:
    """Tests for the query_doctor_report management command."""

    def test_command_runs_without_error(self, tmp_path):
        """Management command executes without errors."""
        from io import StringIO

        from django.core.management import call_command

        output_path = str(tmp_path / "test_cmd.html")
        out = StringIO()

        call_command("query_doctor_report", f"--output={output_path}", stdout=out)

        output = out.getvalue()
        assert "Report generated" in output

    def test_command_creates_file(self, tmp_path):
        """Management command creates the HTML file."""
        from io import StringIO

        from django.core.management import call_command

        output_path = str(tmp_path / "test_cmd_file.html")
        call_command("query_doctor_report", f"--output={output_path}", stdout=StringIO())

        assert os.path.exists(output_path)
        with open(output_path) as f:
            html = f.read()
        assert "<html" in html
