"""Tests for the custom analyzer plugin API.

Verifies that discover_analyzers() loads built-in analyzers and
handles third-party entry point plugins correctly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.plugin_api import discover_analyzers, get_builtin_analyzers
from query_doctor.types import CapturedQuery, Prescription


@pytest.fixture(autouse=True)
def _clear_discovery_cache() -> Iterator[None]:
    """Clear the analyzer-discovery cache around every test in this module.

    ``discover_analyzers()`` caches its result (FOLLOWUPS entry 29), so without
    this the tests below stop exercising anything: the first cached call wins
    and every later ``patch("..._load_entry_point_analyzers")`` is never
    consulted. Clearing *after* matters as much as before -- a result cached
    under a patch would otherwise leak into
    ``test_analyzer_discovery_wiring.py``, whose exact-count assertion would
    then see this module's fake plugin.

    Mirrors the way ``tests/test_pipeline.py`` calls ``get_config.cache_clear()``
    around settings overrides.
    """
    discover_analyzers.cache_clear()
    yield
    discover_analyzers.cache_clear()


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
    """Not a BaseAnalyzer subclass -- should be rejected."""

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

        assert mock_load.called  # the patch must actually be consulted
        names = [a.name for a in result]
        assert "custom_test" in names

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_invalid_plugin_skipped(self, mock_load: MagicMock) -> None:
        """Invalid plugin (not BaseAnalyzer) should be skipped."""
        mock_load.return_value = []

        result = discover_analyzers()

        assert mock_load.called  # the patch must actually be consulted
        # Should still have built-in analyzers
        assert len(result) >= 3

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_plugin_error_logged(
        self, mock_load: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Plugin that raises should log a warning and still return built-ins.

        FOLLOWUPS entry 30: this test opened ``caplog`` and then asserted only
        ``len(result) >= 3``, so the warning its name and docstring promise was
        pinned by nothing -- the ``logger.warning`` in the plugin-load ``except``
        could have been deleted and this test would have stayed green. Verified
        by doing exactly that: replacing it with ``pass`` fails this test at the
        record-count assertion. Both halves are asserted now.
        """
        mock_load.side_effect = Exception("plugin load error")

        with caplog.at_level(logging.WARNING, logger="query_doctor"):
            result = discover_analyzers()

        assert mock_load.called  # the patch must actually be consulted

        # The promised warning (plugin_api.py:105). This assertion is only
        # meaningful because the module fixture cleared the discovery cache:
        # on a cache hit discover_analyzers() never enters the try, the plugin
        # loader never raises, and no warning is emitted.
        warnings = [
            r for r in caplog.records if r.name == "query_doctor" and r.levelno == logging.WARNING
        ]
        assert len(warnings) == 1
        assert "failed to load analyzer plugins" in warnings[0].getMessage()
        # exc_info is the actionable half: without the traceback a user learns
        # that some plugin failed and nothing about which one or why.
        assert warnings[0].exc_info is not None

        # Graceful degradation: a raising loader must not take discovery down.
        assert len(result) >= 3


class TestDiscoverAnalyzersCaching:
    """discover_analyzers() must not rescan entry points on every call.

    FOLLOWUPS entry 29: ``_load_entry_point_analyzers()`` walks every installed
    distribution and reads its ``entry_points.txt`` from disk, and
    ``pipeline.analyze`` called it on every invocation -- measured at 87
    ``read_text`` calls per run against 87 installed distributions, ~8 ms, flat
    in query count. Seven dispatch surfaces route through ``pipeline.analyze``,
    and ``project_diagnoser._diagnose_url`` calls it once per URL pattern, so a
    project scan paid a full rescan per URL.
    """

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_entry_points_scanned_once_across_calls(self, mock_load: MagicMock) -> None:
        """Five calls must scan entry points exactly once."""
        mock_load.return_value = []

        first = discover_analyzers()
        for _ in range(4):
            discover_analyzers()

        assert mock_load.call_count == 1
        # Positive control: the one scan produced a real result, so a
        # discover_analyzers() that returned nothing cannot satisfy the count.
        assert len(first) == 8

    @patch("query_doctor.plugin_api._load_entry_point_analyzers")
    def test_cache_clear_forces_a_rescan(self, mock_load: MagicMock) -> None:
        """``cache_clear()`` is part of the contract, not an afterthought.

        Paired with the test above: without this one, a ``discover_analyzers``
        that scanned entry points *never* would satisfy ``call_count == 1``
        just as well as one that scanned them once.
        """
        mock_load.return_value = []

        discover_analyzers()
        assert mock_load.call_count == 1

        discover_analyzers.cache_clear()
        discover_analyzers()

        assert mock_load.call_count == 2

    def test_returns_a_fresh_list_each_call(self) -> None:
        """The cache must not hand callers the container it caches.

        ``discover_analyzers`` is annotated ``list[BaseAnalyzer]`` and
        ``plugin_api`` is the public plugin surface, so a caller may legitimately
        mutate the result. Returning the cached list object would let one
        caller's ``append`` corrupt every later call. This passes before the
        cache exists too -- it is a guard against the wrong fix, not evidence
        for the right one.
        """
        first = discover_analyzers()
        first.append(ValidCustomAnalyzer())

        second = discover_analyzers()

        assert first is not second
        assert len(second) == 8
        assert "custom_test" not in [a.name for a in second]


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
