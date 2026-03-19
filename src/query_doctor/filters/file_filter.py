"""Per-file and per-module prescription filtering.

Filters prescriptions based on their callsite file path or module name.
Applied post-collection, before reporting — all queries are still
intercepted and analyzed, but the reporter only shows prescriptions
matching the filter criteria.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from query_doctor.types import Prescription


class PrescriptionFilter:
    """Filters prescriptions by file path or module name patterns.

    Supports substring matching: --file=views matches myapp/views.py.
    Multiple patterns are OR'd together — a prescription matching any
    pattern is included.

    Args:
        file_patterns: List of file path substrings to match.
        module_patterns: List of module name substrings to match.
    """

    def __init__(
        self,
        file_patterns: list[str] | None = None,
        module_patterns: list[str] | None = None,
    ) -> None:
        """Initialize the filter.

        Args:
            file_patterns: File path substrings to match against callsite.filepath.
            module_patterns: Module name substrings to match against callsite filepath
                             converted to module notation.
        """
        self.file_patterns = file_patterns or []
        self.module_patterns = module_patterns or []

    @property
    def is_active(self) -> bool:
        """Return True if any filter patterns are configured.

        When no patterns are set, the filter is inactive and matches everything.
        """
        return bool(self.file_patterns or self.module_patterns)

    def matches(self, prescription: Prescription) -> bool:
        """Check if a prescription matches the filter criteria.

        If no patterns are configured, all prescriptions match (no filter).
        Otherwise, the prescription must match at least one file or module pattern.

        Args:
            prescription: The prescription to check.

        Returns:
            True if the prescription matches the filter or no filter is active.
        """
        if not self.is_active:
            return True

        callsite = prescription.callsite
        if callsite is None:
            return False

        filepath = callsite.filepath or ""

        # Check file patterns (substring match)
        for pattern in self.file_patterns:
            if pattern in filepath:
                return True

        # Check module patterns (convert filepath to module-like notation)
        module_path = self._filepath_to_module(filepath)
        return any(pattern in module_path for pattern in self.module_patterns)

    def filter(self, prescriptions: list[Prescription]) -> list[Prescription]:
        """Filter a list of prescriptions, returning only matches.

        Args:
            prescriptions: The full list of prescriptions to filter.

        Returns:
            A new list containing only prescriptions matching the filter.
        """
        return [p for p in prescriptions if self.matches(p)]

    @staticmethod
    def _filepath_to_module(filepath: str) -> str:
        """Convert a file path to a Python module-like notation.

        Replaces path separators with dots and removes .py extension.
        E.g., 'myapp/views.py' → 'myapp.views'

        Args:
            filepath: The file path to convert.

        Returns:
            A dot-separated module-like string.
        """
        # Normalize separators
        module = filepath.replace("\\", "/")

        # Remove .py extension
        if module.endswith(".py"):
            module = module[:-3]

        # Replace / with .
        module = module.replace("/", ".")

        return module
