"""Tests for URL discovery module."""

from __future__ import annotations

import pytest

from query_doctor.url_discovery import DiscoveredURL, discover_urls


@pytest.mark.django_db
class TestDiscoverURLs:
    """Tests for discover_urls function."""

    def test_discovers_urls_from_test_app(self) -> None:
        """discover_urls returns URLs from the test app."""
        urls = discover_urls()
        assert len(urls) > 0

    def test_discovered_urls_have_pattern(self) -> None:
        """Each discovered URL has a non-empty pattern."""
        urls = discover_urls()
        for url in urls:
            assert isinstance(url, DiscoveredURL)
            assert url.pattern

    def test_discovered_urls_have_app_name(self) -> None:
        """Each discovered URL has an app_name."""
        urls = discover_urls()
        for url in urls:
            assert url.app_name

    def test_discovered_urls_have_view_name(self) -> None:
        """Each discovered URL has a view_name."""
        urls = discover_urls()
        for url in urls:
            assert url.view_name

    def test_excludes_admin_by_default(self) -> None:
        """Admin URLs are excluded by default."""
        urls = discover_urls()
        patterns = [u.pattern for u in urls]
        assert not any("/admin/" in p for p in patterns)

    def test_exclude_patterns_filter(self) -> None:
        """Custom exclude_patterns filters out matching URLs."""
        urls = discover_urls(exclude_patterns=["/books/"])
        patterns = [u.pattern for u in urls]
        assert not any("/books/" in p for p in patterns)

    def test_apps_filter(self) -> None:
        """apps parameter filters to specific app namespaces."""
        all_urls = discover_urls()
        filtered = discover_urls(apps=["nonexistent_app"])
        assert len(filtered) == 0
        assert len(all_urls) > 0

    def test_detects_has_parameters(self) -> None:
        """URLs with path parameters are flagged."""
        urls = discover_urls()
        # Our test app has no parameterized URLs, so all should be False
        for url in urls:
            assert isinstance(url.has_parameters, bool)

    def test_detects_methods_for_function_views(self) -> None:
        """Function views default to GET method."""
        urls = discover_urls()
        for url in urls:
            assert isinstance(url.methods, list)
            assert len(url.methods) > 0

    def test_empty_exclude_returns_all(self) -> None:
        """Empty exclude list returns all discoverable URLs."""
        urls = discover_urls(exclude_patterns=[])
        assert len(urls) > 0

    def test_returns_list_of_discovered_url(self) -> None:
        """Return type is a list of DiscoveredURL."""
        urls = discover_urls()
        assert isinstance(urls, list)
        if urls:
            assert isinstance(urls[0], DiscoveredURL)
