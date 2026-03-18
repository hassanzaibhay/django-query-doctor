"""Auto-fix engine for django-query-doctor.

Converts diagnosed prescriptions into concrete code changes. Supports
generating unified diffs and optionally applying fixes to source files
with backup support.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from query_doctor.types import IssueType, Prescription

logger = logging.getLogger("query_doctor")


@dataclass
class ProposedFix:
    """A single proposed code change."""

    file_path: str
    original_line: str
    fixed_line: str
    line_number: int
    description: str
    prescription: Prescription


class QueryFixer:
    """Generates and optionally applies code fixes from prescriptions.

    Parses fix suggestions from prescriptions into concrete line-level
    changes, generates unified diffs, and can write changes to disk.
    """

    def generate_fixes(self, prescriptions: list[Prescription]) -> list[ProposedFix]:
        """Convert prescriptions into concrete code changes.

        Args:
            prescriptions: List of prescriptions with fix suggestions.

        Returns:
            List of ProposedFix objects for applicable prescriptions.
        """
        fixes: list[ProposedFix] = []
        for rx in prescriptions:
            if not rx.callsite or not rx.fix_suggestion:
                continue
            try:
                fix = self._parse_fix(rx)
                if fix:
                    fixes.append(fix)
            except Exception:
                logger.warning(
                    "query_doctor: failed to parse fix for %s",
                    rx.description,
                    exc_info=True,
                )
        return fixes

    def _parse_fix(self, rx: Prescription) -> ProposedFix | None:
        """Parse a prescription's fix_suggestion into a ProposedFix.

        Args:
            rx: The prescription to parse.

        Returns:
            ProposedFix if parseable, None otherwise.
        """
        assert rx.callsite is not None

        filepath = Path(rx.callsite.filepath)
        if not filepath.exists():
            logger.warning("query_doctor: file not found: %s", rx.callsite.filepath)
            return None

        try:
            lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            return None

        line_idx = rx.callsite.line_number - 1
        if line_idx < 0 or line_idx >= len(lines):
            return None

        original_line = lines[line_idx]

        if rx.issue_type in (IssueType.N_PLUS_ONE, IssueType.DRF_SERIALIZER):
            fixed_line = self._fix_nplusone(original_line, rx.fix_suggestion)
        elif rx.issue_type == IssueType.DUPLICATE_QUERY:
            fixed_line = self._fix_duplicate(original_line)
        elif rx.issue_type == IssueType.FAT_SELECT:
            fixed_line = self._fix_fat_select(original_line, rx.fix_suggestion)
        elif rx.issue_type == IssueType.QUERYSET_EVAL:
            fixed_line = self._fix_queryset_eval(original_line, rx.fix_suggestion)
        elif rx.issue_type == IssueType.MISSING_INDEX:
            fixed_line = self._fix_missing_index(original_line, rx.fix_suggestion)
        else:
            return None

        if fixed_line == original_line:
            return None

        return ProposedFix(
            file_path=str(filepath),
            original_line=original_line,
            fixed_line=fixed_line,
            line_number=rx.callsite.line_number,
            description=rx.description,
            prescription=rx,
        )

    def _fix_nplusone(self, line: str, suggestion: str) -> str:
        """Add select_related or prefetch_related to a queryset line.

        Args:
            line: The original source line.
            suggestion: The fix suggestion text.

        Returns:
            Modified line with the optimization added.
        """
        # Extract the method call from suggestion
        sr_match = re.search(r"\.select_related\([^)]*\)", suggestion)
        pr_match = re.search(r"\.prefetch_related\([^)]*\)", suggestion)
        method_call = ""
        if sr_match:
            method_call = sr_match.group(0)
        elif pr_match:
            method_call = pr_match.group(0)

        if not method_call:
            # Try to extract field name
            field_match = re.search(r"select_related\('(\w+)'\)", suggestion)
            if field_match:
                method_call = f".select_related('{field_match.group(1)}')"
            else:
                field_match = re.search(r"prefetch_related\('(\w+)'\)", suggestion)
                if field_match:
                    method_call = f".prefetch_related('{field_match.group(1)}')"

        if not method_call:
            return line

        # Find queryset patterns and insert before terminal operations
        # Pattern: .objects.all(), .objects.filter(...), .objects.exclude(...)
        # Insert before the newline/end
        stripped = line.rstrip("\n")
        if stripped.rstrip().endswith(")"):
            # Insert before the last closing if it's a queryset call
            return stripped + method_call + "\n"
        return stripped + method_call + "\n"

    def _fix_duplicate(self, line: str) -> str:
        """Add TODO comment for duplicate query.

        Args:
            line: The original source line.

        Returns:
            Line with TODO comment prepended.
        """
        indent = len(line) - len(line.lstrip())
        prefix = line[:indent]
        return f"{prefix}# TODO: Cache this query result to avoid duplicate execution\n{line}"

    def _fix_fat_select(self, line: str, suggestion: str) -> str:
        """Add .only() or .defer() to a queryset line.

        Args:
            line: The original source line.
            suggestion: The fix suggestion containing field names.

        Returns:
            Modified line with .only() or .defer() added.
        """
        only_match = re.search(r"\.only\([^)]*\)", suggestion)
        defer_match = re.search(r"\.defer\([^)]*\)", suggestion)

        method_call = ""
        if only_match:
            method_call = only_match.group(0)
        elif defer_match:
            method_call = defer_match.group(0)

        if not method_call:
            return line

        stripped = line.rstrip("\n")
        return stripped + method_call + "\n"

    def _fix_queryset_eval(self, line: str, suggestion: str) -> str:
        """Replace inefficient queryset evaluation patterns.

        Args:
            line: The original source line.
            suggestion: The fix suggestion text.

        Returns:
            Modified line with efficient pattern.
        """
        fixed = line
        # Replace len(something) with something.count()
        if "len(" in line and "count()" in suggestion.lower():
            fixed = re.sub(
                r"len\((\w+)\)",
                r"\1.count()",
                fixed,
            )
        # Replace if qs: with if qs.exists():
        if "exists()" in suggestion.lower():
            fixed = re.sub(
                r"if\s+(\w+)\s*:",
                r"if \1.exists():",
                fixed,
            )
        return fixed

    def _fix_missing_index(self, line: str, suggestion: str) -> str:
        """Add comment about missing index.

        Args:
            line: The original source line.
            suggestion: The fix suggestion text.

        Returns:
            Line with index suggestion comment.
        """
        indent = len(line) - len(line.lstrip())
        prefix = line[:indent]
        return f"{prefix}# TODO: Consider adding an index via Meta.indexes — {suggestion}\n{line}"

    def generate_diff(self, fixes: list[ProposedFix]) -> str:
        """Generate a unified diff string from proposed fixes.

        Args:
            fixes: List of proposed fixes.

        Returns:
            Unified diff as a string.
        """
        if not fixes:
            return "No fixes to apply.\n"

        parts: list[str] = []
        for fix in fixes:
            parts.append(f"--- {fix.file_path}")
            parts.append(f"+++ {fix.file_path}")
            parts.append(f"@@ -{fix.line_number},1 +{fix.line_number},1 @@")
            parts.append(f"  [{fix.description}]")
            parts.append(f"- {fix.original_line.rstrip()}")
            for fixed in fix.fixed_line.splitlines():
                parts.append(f"+ {fixed}")
        return "\n".join(parts) + "\n"

    def apply_fixes(
        self,
        fixes: list[ProposedFix],
        backup: bool = True,
    ) -> list[str]:
        """Write fixes to disk.

        Args:
            fixes: List of proposed fixes to apply.
            backup: If True, create .bak backup files before modifying.

        Returns:
            List of modified file paths.
        """
        modified: list[str] = []

        # Group fixes by file
        by_file: dict[str, list[ProposedFix]] = {}
        for fix in fixes:
            by_file.setdefault(fix.file_path, []).append(fix)

        for filepath, file_fixes in by_file.items():
            try:
                path = Path(filepath)
                if not path.exists():
                    logger.warning(
                        "query_doctor: cannot apply fix — file not found: %s",
                        filepath,
                    )
                    continue

                if backup:
                    shutil.copy2(filepath, filepath + ".bak")

                lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

                # Sort fixes by line number in reverse to avoid offset issues
                sorted_fixes = sorted(file_fixes, key=lambda f: f.line_number, reverse=True)
                for fix in sorted_fixes:
                    idx = fix.line_number - 1
                    if 0 <= idx < len(lines):
                        lines[idx] = fix.fixed_line

                path.write_text("".join(lines), encoding="utf-8")
                modified.append(filepath)
            except Exception:
                logger.warning(
                    "query_doctor: failed to apply fix to %s",
                    filepath,
                    exc_info=True,
                )

        return modified
