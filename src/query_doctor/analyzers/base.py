"""Base class for all query analyzers.

Defines the interface that all analyzers must implement.
Each analyzer detects one type of query optimization issue.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from query_doctor.types import CapturedQuery, Prescription


class BaseAnalyzer(ABC):
    """Base class for all query analyzers."""

    name: str = ""

    @abstractmethod
    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze captured queries and return prescriptions.

        Args:
            queries: List of captured SQL queries to analyze.
            models_meta: Reserved, and **currently always None**. Nothing in
                the package passes it: the single call site,
                ``pipeline.analyze()``, calls ``analyzer.analyze(queries)``
                for every analyzer on every run. Do not write a plugin that
                depends on receiving a value here. Accept the parameter so
                your signature stays compatible; removing it from the
                contract would be a breaking change and is deferred to 3.0.

        Returns:
            List of Prescription objects describing detected issues and fixes.
        """
        ...

    def is_enabled(self) -> bool:
        """Check if this analyzer is enabled in config."""
        from query_doctor.conf import get_config

        config = get_config()
        analyzer_config = config.get("ANALYZERS", {}).get(self.name, {})
        return bool(analyzer_config.get("enabled", True))
