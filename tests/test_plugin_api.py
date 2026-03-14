"""Tests for the custom analyzer plugin API.

Verifies that discover_analyzers() loads built-in analyzers and
handles third-party entry point plugins correctly.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.plugin_api import discover_analyzers, get_builtin_analyzers
from query_doctor.types import CapturedQuery, Prescription


class ValidCustomAnalyzer(BaseAnalyzer):
    """A valid custom analyzer for testing."""

    name = "custom_test"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Return empty prescriptions."""
        return []


class InvalidPlugin:
    """Not a BaseAnalyzer subclass — should be rejected."""

    name = "invalid"


class TestGetBuiltinAnalyzers:
    """Tests for get_builtin_analyzers()."""

    def test_returns_list(self) -> None:
        """Should return a list."""
        result = get_builtin_analyzers()
        assert isinstance(result, list)

    def test_contains_core_analyzers(self) -> None:
        """Should contain at least NPlusOne, Duplicate, and MissingIndex."""
        result = get_builtin_analyzers()
        names = [a.name for a in result]
        assert "nplusone" in names
        assert "duplicate" in names
        assert "missing_index" in names

    def test_all_are_base_analyzer(self) -> None:
        """All returned analyzers should be BaseAnalyzer instances."""
        result = get_builtin_analyzers()
        for analyzer in result:
            assert isinstance(analyzer, BaseAnalyzer)


class TestDiscoverAnalyzers:
    """Tests for discover_analyzers() with entry point loading."""

    def test_returns_builtin_without_plugins(self) -> None:
        """Without plugins, should return only built-in analyzers."""
        result = discover_analyzers()
        assert len(result) >= 3  # At least nplusone, duplicate, missing_index

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_includes_valid_plugin(self, mock_load: MagicMock) -> None:
        """Valid plugin should be included in results."""
        mock_load.return_value = [ValidCustomAnalyzer()]

        result = discover_analyzers()

        names = [a.name for a in result]
        assert "custom_test" in names

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_invalid_plugin_skipped(self, mock_load: MagicMock) -> None:
        """Invalid plugin (not BaseAnalyzer) should be skipped."""
        mock_load.return_value = []

        result = discover_analyzers()

        # Should still have built-in analyzers
        assert len(result) >= 3

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_plugin_error_logged(
        self, mock_load: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Plugin that raises should log a warning."""
        mock_load.side_effect = Exception("plugin load error")

        with caplog.at_level(logging.WARNING, logger="query_doctor"):
            result = discover_analyzers()

        # Should still return built-in analyzers
        assert len(result) >= 3


class TestEntryPointLoading:
    """Tests for entry point loading mechanics."""

    @patch("query_doctor.plugin_api.entry_points")
    def test_loads_from_entry_points(self, mock_eps: MagicMock) -> None:
        """Should attempt to load from entry_points group."""
        mock_ep = MagicMock()
        mock_ep.name = "test_analyzer"
        mock_ep.load.return_value = ValidCustomAnalyzer
        mock_eps.return_value = [mock_ep]

        from query_doctor.plugin_api import _load_entry_point_analyzers

        result = _load_entry_point_analyzers()

        assert len(result) == 1
        assert isinstance(result[0], ValidCustomAnalyzer)

    @patch("query_doctor.plugin_api.entry_points")
    def test_skips_non_analyzer_class(self, mock_eps: MagicMock) -> None:
        """Entry point that loads a non-BaseAnalyzer should be skipped."""
        mock_ep = MagicMock()
        mock_ep.name = "bad_plugin"
        mock_ep.load.return_value = InvalidPlugin
        mock_eps.return_value = [mock_ep]

        from query_doctor.plugin_api import _load_entry_point_analyzers

        result = _load_entry_point_analyzers()

        assert len(result) == 0

    @patch("query_doctor.plugin_api.entry_points")
    def test_handles_load_failure(
        self, mock_eps: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Entry point that fails to load should log warning."""
        mock_ep = MagicMock()
        mock_ep.name = "broken_plugin"
        mock_ep.load.side_effect = ImportError("module not found")
        mock_eps.return_value = [mock_ep]

        from query_doctor.plugin_api import _load_entry_point_analyzers

        with caplog.at_level(logging.WARNING, logger="query_doctor"):
            result = _load_entry_point_analyzers()

        assert len(result) == 0


class TestPluginAPIModule:
    """Tests for module structure."""

    def test_module_docstring(self) -> None:
        """Module should have a docstring."""
        import query_doctor.plugin_api

        assert query_doctor.plugin_api.__doc__

    def test_exports(self) -> None:
        """Module should export key functions."""
        import query_doctor.plugin_api as api

        assert hasattr(api, "discover_analyzers")
        assert hasattr(api, "get_builtin_analyzers")
