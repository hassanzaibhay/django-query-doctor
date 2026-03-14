"""Tests for the query complexity analyzer."""

from __future__ import annotations

from query_doctor.analyzers.complexity import QueryComplexityAnalyzer
from query_doctor.types import CallSite, CapturedQuery, IssueType, Severity


def _make_query(sql: str) -> CapturedQuery:
    """Create a CapturedQuery from raw SQL for testing."""
    return CapturedQuery(
        sql=sql,
        params=None,
        duration_ms=1.0,
        fingerprint="abc123",
        normalized_sql=sql.lower(),
        callsite=CallSite(
            filepath="myapp/views.py",
            line_number=10,
            function_name="get_queryset",
        ),
        is_select=sql.strip().upper().startswith("SELECT"),
        tables=["books"],
    )


class TestQueryComplexityScoring:
    """Tests for complexity scoring logic."""

    def test_simple_select_low_score(self) -> None:
        """Simple SELECT should not be flagged."""
        analyzer = QueryComplexityAnalyzer()
        query = _make_query("SELECT id, title FROM books WHERE id = ?")
        result = analyzer.analyze([query])
        assert len(result) == 0

    def test_query_with_four_joins_flagged(self) -> None:
        """Query with 4 JOINs should be flagged."""
        analyzer = QueryComplexityAnalyzer()
        sql = (
            "SELECT b.id FROM books b "
            "JOIN authors a ON b.author_id = a.id "
            "JOIN publishers p ON b.publisher_id = p.id "
            "JOIN categories c ON c.book_id = b.id "
            "JOIN tags t ON t.book_id = b.id "
            "WHERE b.id = ?"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) == 1
        assert result[0].issue_type == IssueType.QUERY_COMPLEXITY

    def test_subquery_adds_points(self) -> None:
        """Subqueries should add complexity points."""
        analyzer = QueryComplexityAnalyzer()
        sql = "SELECT id FROM books WHERE author_id IN (SELECT id FROM authors WHERE country = ?)"
        score = analyzer._score_complexity(sql.lower())
        # subquery = 3 points
        assert score >= 3

    def test_group_by_having_order_by_cumulative(self) -> None:
        """GROUP BY + HAVING + ORDER BY should accumulate points."""
        analyzer = QueryComplexityAnalyzer()
        sql = (
            "SELECT author_id, COUNT(*) FROM books "
            "JOIN authors a ON books.author_id = a.id "
            "JOIN publishers p ON a.publisher_id = p.id "
            "GROUP BY author_id "
            "HAVING COUNT(*) > 5 "
            "ORDER BY COUNT(*) DESC"
        )
        score = analyzer._score_complexity(sql.lower())
        # 2 JOINs (4) + GROUP BY (2) + HAVING (2) + ORDER BY (1) = 9
        assert score >= 8

    def test_threshold_boundary_at_threshold_flagged(self) -> None:
        """Score exactly at threshold should be flagged."""
        analyzer = QueryComplexityAnalyzer()
        # 4 JOINs = 8 points = default threshold
        sql = (
            "SELECT b.id FROM books b "
            "JOIN authors a ON b.author_id = a.id "
            "JOIN publishers p ON b.publisher_id = p.id "
            "JOIN categories c ON c.book_id = b.id "
            "JOIN tags t ON t.book_id = b.id"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) == 1

    def test_threshold_boundary_below_not_flagged(self) -> None:
        """Score below threshold should not be flagged."""
        analyzer = QueryComplexityAnalyzer()
        # 3 JOINs = 6 points, below default threshold of 8
        sql = (
            "SELECT b.id FROM books b "
            "JOIN authors a ON b.author_id = a.id "
            "JOIN publishers p ON b.publisher_id = p.id "
            "JOIN categories c ON c.book_id = b.id"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) == 0

    def test_config_disabled_returns_empty(self, settings: object) -> None:
        """Disabled analyzer returns no prescriptions."""
        from django.test import override_settings

        with override_settings(
            QUERY_DOCTOR={
                "ANALYZERS": {"complexity": {"enabled": False}},
            }
        ):
            from query_doctor.conf import get_config

            get_config.cache_clear()
            analyzer = QueryComplexityAnalyzer()
            sql = (
                "SELECT b.id FROM books b "
                "JOIN a ON 1=1 JOIN b2 ON 1=1 JOIN c ON 1=1 "
                "JOIN d ON 1=1 JOIN e ON 1=1"
            )
            query = _make_query(sql)
            result = analyzer.analyze([query])
            assert len(result) == 0
            get_config.cache_clear()

    def test_custom_threshold_via_config(self, settings: object) -> None:
        """Custom threshold should be respected."""
        from django.test import override_settings

        with override_settings(
            QUERY_DOCTOR={
                "ANALYZERS": {"complexity": {"enabled": True, "threshold": 4}},
            }
        ):
            from query_doctor.conf import get_config

            get_config.cache_clear()
            analyzer = QueryComplexityAnalyzer()
            # 2 JOINs = 4 points, which matches threshold of 4
            sql = (
                "SELECT b.id FROM books b "
                "JOIN authors a ON b.author_id = a.id "
                "JOIN publishers p ON b.publisher_id = p.id"
            )
            query = _make_query(sql)
            result = analyzer.analyze([query])
            assert len(result) == 1
            get_config.cache_clear()

    def test_critical_severity_for_high_score(self) -> None:
        """Score >= 12 should be CRITICAL."""
        analyzer = QueryComplexityAnalyzer()
        sql = (
            "SELECT b.id FROM books b "
            "JOIN a1 ON 1=1 JOIN a2 ON 1=1 JOIN a3 ON 1=1 "
            "JOIN a4 ON 1=1 JOIN a5 ON 1=1 JOIN a6 ON 1=1 "
            "WHERE x = ?"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) == 1
        assert result[0].severity == Severity.CRITICAL

    def test_warning_severity_for_moderate_score(self) -> None:
        """Score between threshold and 12 should be WARNING."""
        analyzer = QueryComplexityAnalyzer()
        # 4 JOINs = 8 points, below 12
        sql = (
            "SELECT b.id FROM books b JOIN a1 ON 1=1 JOIN a2 ON 1=1 JOIN a3 ON 1=1 JOIN a4 ON 1=1"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) == 1
        assert result[0].severity == Severity.WARNING

    def test_fix_suggestions_mention_joins(self) -> None:
        """Fix suggestions should mention JOINs when many JOINs detected."""
        analyzer = QueryComplexityAnalyzer()
        sql = (
            "SELECT b.id FROM books b JOIN a1 ON 1=1 JOIN a2 ON 1=1 JOIN a3 ON 1=1 JOIN a4 ON 1=1"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) == 1
        assert "join" in result[0].fix_suggestion.lower() or "JOIN" in result[0].fix_suggestion

    def test_fix_suggestions_mention_or(self) -> None:
        """Fix suggestions should mention OR when many OR conditions."""
        analyzer = QueryComplexityAnalyzer()
        sql = (
            "SELECT b.id FROM books b "
            "JOIN a1 ON 1=1 JOIN a2 ON 1=1 JOIN a3 ON 1=1 "
            "WHERE x = 1 OR y = 2 OR z = 3 OR w = 4"
        )
        query = _make_query(sql)
        result = analyzer.analyze([query])
        assert len(result) >= 1
        assert "or" in result[0].fix_suggestion.lower()

    def test_non_select_queries_skipped(self) -> None:
        """Non-SELECT queries should be skipped."""
        analyzer = QueryComplexityAnalyzer()
        query = CapturedQuery(
            sql="INSERT INTO books (title) VALUES (?)",
            params=None,
            duration_ms=1.0,
            fingerprint="abc123",
            normalized_sql="insert into books (title) values (?)",
            callsite=None,
            is_select=False,
            tables=["books"],
        )
        result = analyzer.analyze([query])
        assert len(result) == 0

    def test_distinct_adds_points(self) -> None:
        """DISTINCT should add complexity points."""
        analyzer = QueryComplexityAnalyzer()
        score = analyzer._score_complexity("select distinct id from books")
        assert score >= 1

    def test_union_adds_points(self) -> None:
        """UNION should add complexity points."""
        analyzer = QueryComplexityAnalyzer()
        score = analyzer._score_complexity("select id from books union select id from categories")
        assert score >= 3

    def test_like_leading_wildcard_adds_points(self) -> None:
        """LIKE with leading % should add complexity points."""
        analyzer = QueryComplexityAnalyzer()
        score = analyzer._score_complexity("select id from books where title like '%search%'")
        assert score >= 2

    def test_case_when_adds_points(self) -> None:
        """CASE/WHEN adds complexity points."""
        analyzer = QueryComplexityAnalyzer()
        score = analyzer._score_complexity(
            "select case when status = 1 then 'a' when status = 2 then 'b' end from books"
        )
        assert score >= 2
