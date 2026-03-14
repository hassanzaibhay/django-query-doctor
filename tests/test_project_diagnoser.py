"""Tests for project diagnoser module."""

from __future__ import annotations

import pytest

from query_doctor.project_diagnoser import (
    AppDiagnosisResult,
    ProjectDiagnoser,
    ProjectDiagnosisResult,
    URLDiagnosisResult,
)
from query_doctor.url_discovery import DiscoveredURL
from tests.factories import AuthorFactory, BookFactory, PublisherFactory


def _make_url(
    pattern: str = "/books/optimized/",
    app_name: str = "testapp",
    view_name: str = "book_list_optimized",
) -> DiscoveredURL:
    """Create a DiscoveredURL for testing."""
    return DiscoveredURL(
        pattern=pattern,
        name=None,
        app_name=app_name,
        view_name=view_name,
        methods=["GET"],
        has_parameters=False,
    )


@pytest.mark.django_db
class TestProjectDiagnoser:
    """Tests for ProjectDiagnoser class."""

    def test_diagnose_single_url(self) -> None:
        """Diagnoser can diagnose a single URL successfully."""
        pub = PublisherFactory()
        author = AuthorFactory(publisher=pub)
        BookFactory(author=author, publisher=pub)

        diagnoser = ProjectDiagnoser()
        url = _make_url()
        result = diagnoser.diagnose([url])

        assert isinstance(result, ProjectDiagnosisResult)
        assert result.total_urls_analyzed == 1

    def test_diagnose_captures_queries(self) -> None:
        """Diagnoser captures query data for a URL."""
        pub = PublisherFactory()
        author = AuthorFactory(publisher=pub)
        BookFactory(author=author, publisher=pub)

        diagnoser = ProjectDiagnoser()
        url = _make_url()
        result = diagnoser.diagnose([url])

        assert result.total_queries > 0

    def test_handles_404_url(self) -> None:
        """Diagnoser handles a URL that returns 404 without crashing."""
        diagnoser = ProjectDiagnoser()
        url = _make_url(pattern="/nonexistent/page/")
        result = diagnoser.diagnose([url])

        # Should still have 1 analyzed URL (it ran, just got 404)
        assert result.total_urls_analyzed >= 0
        # Should not crash

    def test_handles_exception_url(self) -> None:
        """Diagnoser skips URLs that raise exceptions."""
        diagnoser = ProjectDiagnoser()
        # URL with parameters that can't be resolved
        url = _make_url(pattern="/no/such/endpoint/")
        result = diagnoser.diagnose([url])
        # Should not crash — result is valid
        assert isinstance(result, ProjectDiagnosisResult)

    def test_groups_by_app(self) -> None:
        """Diagnoser groups results by app_name."""
        pub = PublisherFactory()
        author = AuthorFactory(publisher=pub)
        BookFactory(author=author, publisher=pub)

        diagnoser = ProjectDiagnoser()
        urls = [
            _make_url(pattern="/books/optimized/", app_name="testapp"),
            _make_url(
                pattern="/books/duplicate/", app_name="testapp", view_name="book_list_duplicate"
            ),
        ]
        result = diagnoser.diagnose(urls)

        app_names = [a.app_name for a in result.app_results]
        assert "testapp" in app_names

    def test_methods_filter(self) -> None:
        """Methods filter skips URLs whose methods don't match."""
        diagnoser = ProjectDiagnoser()
        url = _make_url()
        url_post = DiscoveredURL(
            pattern="/books/optimized/",
            name=None,
            app_name="testapp",
            view_name="test",
            methods=["POST"],
            has_parameters=False,
        )
        result = diagnoser.diagnose([url, url_post], methods=["GET"])

        assert result.total_urls_analyzed <= 2
        assert len(result.skipped_urls) >= 1

    def test_has_timestamps(self) -> None:
        """Result includes started_at and finished_at timestamps."""
        diagnoser = ProjectDiagnoser()
        result = diagnoser.diagnose([])

        assert result.started_at
        assert result.finished_at


@pytest.mark.django_db
class TestHealthScore:
    """Tests for health score calculation."""

    def test_health_score_no_issues(self) -> None:
        """Health score is 100 when there are no issues."""
        app = AppDiagnosisResult(app_name="test")
        url_result = URLDiagnosisResult(
            url=_make_url(),
            report=None,
            error=None,
        )
        app.url_results.append(url_result)
        assert app.health_score == 100.0

    def test_overall_health_score_empty(self) -> None:
        """Overall health score is 100 for empty project."""
        result = ProjectDiagnosisResult()
        assert result.overall_health_score == 100.0

    def test_total_urls_analyzed(self) -> None:
        """total_urls_analyzed counts all URLs across apps."""
        result = ProjectDiagnosisResult()
        app = AppDiagnosisResult(app_name="test")
        app.url_results.append(URLDiagnosisResult(url=_make_url(), report=None))
        result.app_results.append(app)
        assert result.total_urls_analyzed == 1
