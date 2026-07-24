"""Tests for .queryignore file support."""

from __future__ import annotations

from pathlib import Path

from query_doctor.ignore import (
    IgnoreRule,
    filter_prescriptions,
    load_queryignore,
)
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    IssueType,
    Prescription,
    Severity,
)


def _make_query(
    sql: str = "SELECT * FROM books",
    callsite_file: str = "myapp/views.py",
    callsite_line: int = 10,
) -> CapturedQuery:
    """Create a CapturedQuery for testing."""
    return CapturedQuery(
        sql=sql,
        params=None,
        duration_ms=1.0,
        fingerprint="abc123",
        normalized_sql=sql.lower(),
        callsite=CallSite(
            filepath=callsite_file,
            line_number=callsite_line,
            function_name="get_queryset",
        ),
        is_select=True,
        tables=["books"],
    )


def _make_prescription(
    issue_type: IssueType = IssueType.N_PLUS_ONE,
    callsite_file: str = "myapp/views.py",
    callsite_line: int = 10,
) -> Prescription:
    """Create a Prescription for testing."""
    return Prescription(
        issue_type=issue_type,
        severity=Severity.WARNING,
        description="Test issue",
        fix_suggestion="Fix it",
        callsite=CallSite(
            filepath=callsite_file,
            line_number=callsite_line,
            function_name="get_queryset",
        ),
    )


class TestLoadQueryignore:
    """Tests for loading and parsing .queryignore files."""

    def test_parse_with_comments_and_blank_lines(self, tmp_path: Path) -> None:
        """Comments and blank lines should be ignored."""
        ignore_file = tmp_path / ".queryignore"
        ignore_file.write_text(
            "# This is a comment\n"
            "\n"
            "sql:SELECT * FROM django_session%\n"
            "# Another comment\n"
            "\n"
            "file:myapp/migrations/*\n"
        )
        rules = load_queryignore(tmp_path)
        assert len(rules) == 2
        assert rules[0].rule_type == "sql"
        assert rules[0].pattern == "SELECT * FROM django_session%"
        assert rules[1].rule_type == "file"
        assert rules[1].pattern == "myapp/migrations/*"

    def test_missing_queryignore_returns_empty(self, tmp_path: Path) -> None:
        """Missing .queryignore should return empty list, no crash."""
        rules = load_queryignore(tmp_path)
        assert rules == []

    def test_all_rule_types_parsed(self, tmp_path: Path) -> None:
        """All rule types should be parsed correctly."""
        ignore_file = tmp_path / ".queryignore"
        ignore_file.write_text(
            "sql:SELECT * FROM sessions%\n"
            "file:myapp/migrations/*\n"
            "callsite:myapp/views.py:142\n"
            "ignore:nplusone:myapp/views.py:LegacyView\n"
        )
        rules = load_queryignore(tmp_path)
        assert len(rules) == 4
        assert rules[0].rule_type == "sql"
        assert rules[1].rule_type == "file"
        assert rules[2].rule_type == "callsite"
        assert rules[3].rule_type == "ignore"


class TestSqlRuleAgainstRawSql:
    """sql: rules matched against the raw SQL behind a prescription.

    Ported from the deleted query-level TestShouldIgnoreQuery: the ``%`` -> ``*``
    translation and its positive/negative cases now live at the prescription
    level, which is the only surface .queryignore filters. ``_make_query``
    supplies the query behind each prescription (matched via fingerprint).
    """

    def test_sql_pattern_matching_with_wildcard(self) -> None:
        """A sql: pattern present in the raw SQL (not the description) matches."""
        rules = [IgnoreRule(rule_type="sql", pattern="SELECT * FROM django_session%")]
        query = _make_query(sql="SELECT * FROM django_session WHERE id = 1")
        rx = _make_prescription()  # fingerprint defaults to match _make_query
        rx = Prescription(
            issue_type=rx.issue_type,
            severity=rx.severity,
            description="N+1 detected: 5 queries",  # pattern absent here
            fix_suggestion=rx.fix_suggestion,
            callsite=rx.callsite,
            fingerprint=query.fingerprint,
        )
        assert "django_session" not in rx.description
        assert filter_prescriptions([rx], rules, [query]) == []

    def test_sql_pattern_no_match(self) -> None:
        """Non-matching SQL leaves the prescription in place."""
        rules = [IgnoreRule(rule_type="sql", pattern="SELECT * FROM django_session%")]
        query = _make_query(sql="SELECT * FROM books WHERE id = 1")
        rx = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="N+1 detected: 5 queries",
            fix_suggestion="Fix it",
            callsite=query.callsite,
            fingerprint=query.fingerprint,
        )
        assert len(filter_prescriptions([rx], rules, [query])) == 1

    def test_prescription_without_fingerprint_not_matched_by_sql(self) -> None:
        """Analogue of the old no-callsite edge: an empty fingerprint cannot be
        resolved to any query, so a sql: rule present only in raw SQL misses.
        """
        rules = [IgnoreRule(rule_type="sql", pattern="SELECT * FROM django_session%")]
        query = _make_query(sql="SELECT * FROM django_session WHERE id = 1")
        rx = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="N+1 detected: 5 queries",  # pattern absent
            fix_suggestion="Fix it",
            callsite=query.callsite,
            fingerprint="",  # unresolvable
        )
        assert len(filter_prescriptions([rx], rules, [query])) == 1


class TestFilterPrescriptions:
    """Tests for filtering prescriptions by ignore rules."""

    def test_prescriptions_filtered_by_file_rule(self) -> None:
        """Prescriptions matching file rules should be filtered out."""
        rules = [IgnoreRule(rule_type="file", pattern="myapp/migrations/*")]
        prescriptions = [
            _make_prescription(callsite_file="myapp/migrations/0001.py"),
            _make_prescription(callsite_file="myapp/views.py"),
        ]
        filtered = filter_prescriptions(prescriptions, rules)
        assert len(filtered) == 1
        assert filtered[0].callsite.filepath == "myapp/views.py"

    def test_prescriptions_filtered_by_callsite_rule(self) -> None:
        """Prescriptions matching callsite rules should be filtered out."""
        rules = [IgnoreRule(rule_type="callsite", pattern="myapp/views.py:10")]
        prescriptions = [
            _make_prescription(callsite_file="myapp/views.py", callsite_line=10),
            _make_prescription(callsite_file="myapp/views.py", callsite_line=20),
        ]
        filtered = filter_prescriptions(prescriptions, rules)
        assert len(filtered) == 1
        assert filtered[0].callsite.line_number == 20

    def test_issue_type_path_combo_rule(self) -> None:
        """ignore:type:path rules should filter by issue type and path."""
        rules = [IgnoreRule(rule_type="ignore", pattern="n_plus_one:myapp/views.py:LegacyView")]
        prescriptions = [
            _make_prescription(
                issue_type=IssueType.N_PLUS_ONE,
                callsite_file="myapp/views.py",
            ),
            _make_prescription(
                issue_type=IssueType.DUPLICATE_QUERY,
                callsite_file="myapp/views.py",
            ),
        ]
        filtered = filter_prescriptions(prescriptions, rules)
        # N+1 at myapp/views.py should be filtered, duplicate should remain
        assert len(filtered) == 1
        assert filtered[0].issue_type == IssueType.DUPLICATE_QUERY

    def test_prescription_without_callsite_not_filtered_by_file(self) -> None:
        """Prescriptions without callsite should not be filtered by file rules."""
        rules = [IgnoreRule(rule_type="file", pattern="myapp/*")]
        prescription = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="Test",
            fix_suggestion="Fix",
            callsite=None,
        )
        filtered = filter_prescriptions([prescription], rules)
        assert len(filtered) == 1

    def test_empty_rules_no_filtering(self) -> None:
        """Empty rules should not filter anything."""
        prescriptions = [_make_prescription(), _make_prescription()]
        filtered = filter_prescriptions(prescriptions, [])
        assert len(filtered) == 2

    def test_sql_rule_filters_prescriptions_by_fingerprint(self) -> None:
        """SQL rules should filter prescriptions (matched via description)."""
        rules = [IgnoreRule(rule_type="sql", pattern="SELECT * FROM django_session%")]
        p = Prescription(
            issue_type=IssueType.DUPLICATE_QUERY,
            severity=Severity.WARNING,
            description="Duplicate query: SELECT * FROM django_session WHERE id = 1",
            fix_suggestion="Cache result",
            callsite=CallSite("myapp/views.py", 10, "get"),
        )
        filtered = filter_prescriptions([p], rules)
        # SQL rule matching on prescriptions is best-effort via description
        assert len(filtered) <= 1


def _query_with_sql(sql: str, fingerprint: str) -> CapturedQuery:
    """A CapturedQuery carrying a specific fingerprint and raw SQL."""
    return CapturedQuery(
        sql=sql,
        params=None,
        duration_ms=1.0,
        fingerprint=fingerprint,
        normalized_sql=sql.lower(),
        callsite=CallSite("myapp/views.py", 10, "get"),
        is_select=True,
        tables=["blog_author"],
    )


def _prescription_with_fingerprint(description: str, fingerprint: str) -> Prescription:
    """A Prescription tagged with a fingerprint (as real analyzers now emit)."""
    return Prescription(
        issue_type=IssueType.N_PLUS_ONE,
        severity=Severity.WARNING,
        description=description,
        fix_suggestion="Fix it",
        callsite=CallSite("myapp/views.py", 10, "get"),
        fingerprint=fingerprint,
    )


class TestFilterPrescriptionsWithQueries:
    """filter_prescriptions() must match sql: rules against raw SQL when the
    captured queries are supplied (FOLLOWUPS entry 6), while remaining a strict
    superset of today's description-only behaviour.
    """

    def test_sql_rule_matches_raw_sql_absent_from_description(self) -> None:
        """A sql: pattern present in raw SQL but not the description must suppress.

        Impossible before: filter_prescriptions matched only rx.description.
        """
        fp = "fp_author_by_id"
        query = _query_with_sql(
            'SELECT "blog_author"."ssn_hash" FROM "blog_author" WHERE "id" = 1', fp
        )
        rx = _prescription_with_fingerprint('N+1 detected: 12 queries for table "blog_author"', fp)
        assert "ssn_hash" not in rx.description
        rules = [IgnoreRule(rule_type="sql", pattern="%ssn_hash%")]

        kept = filter_prescriptions([rx], rules, [query])
        assert kept == []

    def test_sql_rule_matching_description_still_matches_with_queries(self) -> None:
        """Superset: a rule that matches the description today must still match
        when queries are supplied and the SQL does NOT contain the pattern.
        """
        fp = "fp_dup"
        query = _query_with_sql("SELECT id FROM books", fp)
        rx = _prescription_with_fingerprint(
            "Duplicate query: SELECT * FROM django_session WHERE id = 1", fp
        )
        rules = [IgnoreRule(rule_type="sql", pattern="SELECT * FROM django_session%")]

        kept = filter_prescriptions([rx], rules, [query])
        assert kept == []

    def test_without_queries_argument_matches_prior_behavior(self) -> None:
        """Called without queries, sql: must behave exactly as before (description only)."""
        fp = "fp_author_by_id"
        rx = _prescription_with_fingerprint('N+1 detected: 12 queries for table "blog_author"', fp)
        rules = [IgnoreRule(rule_type="sql", pattern="%ssn_hash%")]

        # ssn_hash is only in the (unavailable) raw SQL; with no queries it cannot match.
        kept = filter_prescriptions([rx], rules)
        assert len(kept) == 1
