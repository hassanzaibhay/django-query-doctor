"""Tests for the anti-staleness gate.

The load-bearing one is :meth:`TestGateCatchesTheDefectsThatMotivatedIt`.
A gate that cannot catch the defects it was built for is theatre, and the
only way to know is to point it at the revision that carried them.
"""

from __future__ import annotations

import subprocess
from typing import ClassVar

import pytest

from scripts.staleness_gate import (
    check_emitted_strings,
    check_version_literals,
    group_by_trigger,
    line_matches_template,
    sweep,
    trigger_of,
)

# The released revision whose defects motivated this gate: B1 (a version
# literal stale for six releases) and B3 (two emitted strings the analyzers
# stopped producing in 2.3.0).
DEFECTIVE_REV = "96cee41"


def _rev_exists() -> bool:
    """Report whether the historical revision is present in this clone."""
    done = subprocess.run(
        ["git", "cat-file", "-e", f"{DEFECTIVE_REV}^{{commit}}"],
        capture_output=True,
    )
    return done.returncode == 0


needs_history = pytest.mark.skipif(
    not _rev_exists(), reason=f"{DEFECTIVE_REV} not present (shallow clone)"
)


class TestGateIsCleanAtHead:
    """The gate must pass on the tree it ships with."""

    def test_no_violations_at_head(self) -> None:
        """A gate that is red on its own tree gets disabled, not fixed."""
        assert sweep() == []


@needs_history
class TestGateCatchesTheDefectsThatMotivatedIt:
    """The acceptance criterion: fails at 96cee41, naming B1 and B3.

    Expressed against a git revision rather than a checkout so it needs no
    worktree and cannot be satisfied by the current tree's contents.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def violations(cls) -> list[str]:
        """Every violation the gate reports at the defective revision."""
        return sweep(DEFECTIVE_REV)

    def test_the_gate_fails_there(self, violations: list[str]) -> None:
        """Sanity: the revision is not clean."""
        assert violations, f"the gate found nothing at {DEFECTIVE_REV}"

    def test_names_b1_the_stale_version_literal(self, violations: list[str]) -> None:
        """B1: the install-verification block showed 1.0.3 against 2.3.0."""
        hits = [v for v in violations if v.startswith("docs/getting-started/installation.md")]
        assert hits, "B1's install-verification line was not caught"
        assert any("1.0.3" in v for v in hits), hits

    def test_names_b1s_two_sibling_version_fields(self, violations: list[str]) -> None:
        """The same defect in the two JSON samples a reporter emits."""
        paths = {v.split(":")[0] for v in violations if "reports version" in v}
        assert {"docs/guides/baseline.md", "docs/reporters/index.md"} <= paths, paths

    def test_names_b3_in_the_readme(self, violations: list[str]) -> None:
        """B3: the headline block quoted both strings 2.3.0 replaced."""
        hits = [v for v in violations if v.startswith("README.md")]
        assert len(hits) >= 2, hits

    def test_names_b3_in_the_generator_and_its_artifacts(self, violations: list[str]) -> None:
        """B3 lived in scripts/ and examples/, which a docs-only gate misses.

        This is the assertion that pins the gate's scope: dropping either
        prefix leaves the root cause and its committed output uncaught.
        """
        paths = {v.split(":")[0] for v in violations}
        assert "examples/generate_svgs.py" in paths, paths
        assert "examples/screenshots/auto_fix.capture.txt" in paths, paths


class TestNonEmptyGapRule:
    """The rule that makes the check discriminating rather than decorative."""

    SEGMENTS: ClassVar[list[str]] = ["Add .", "('", "') to your ", " queryset"]

    def test_the_stale_form_fails(self) -> None:
        """No room for the model name before ` queryset`."""
        assert not line_matches_template(
            "Fix: Add .select_related('author') to your queryset", self.SEGMENTS
        )

    def test_the_current_form_passes(self) -> None:
        """`Book` fills the gap the template leaves."""
        assert line_matches_template(
            "Fix: Add .select_related('author') to your Book queryset", self.SEGMENTS
        )

    def test_a_bare_concatenation_fails(self) -> None:
        """Every segment present, in order, but nothing interpolated."""
        assert not line_matches_template("Add .('') to your  queryset", self.SEGMENTS)

    def test_out_of_order_segments_fail(self) -> None:
        """Order is part of the shape, not incidental."""
        assert not line_matches_template("Add . queryset x ('y') to your ", self.SEGMENTS)

    def test_a_line_without_the_anchor_is_not_matched(self) -> None:
        """Unrelated prose is not this template."""
        assert not line_matches_template("Use .defer('description') instead", self.SEGMENTS)


class TestTriggerSelection:
    """Anchoring on the longest segment, not the first."""

    def test_trigger_is_the_longest_segment(self) -> None:
        """`Add to ` matches prose; the Meta.indexes clause does not."""
        segments = ["Add to ", "'s Meta.indexes: indexes = [models.Index(fields=[\"", '"])]']
        assert trigger_of(segments) == segments[1]

    def test_templates_sharing_a_trigger_are_grouped(self) -> None:
        """Two forms whose longest segment is the same clause share a group."""
        shared = " single-row INSERT statements for "
        a = ["Write N+1 detected: ", shared, ". One bulk statement replaces all "]
        b = ["Write N+1 detected: ", shared, ". Use bulk_create("]
        grouped = group_by_trigger([a, b])
        assert len(grouped[shared]) == 2


class TestSubstringTriggerCollision:
    """A duplicate-query line contains the N+1 trigger as a substring.

    Judging such a line against only the first trigger found reported it as
    stale; it is not, it simply matches a different template.
    """

    def test_a_duplicate_line_is_not_reported_as_a_stale_n_plus_one(self) -> None:
        """The line matches the duplicate template, so it is consistent."""
        nplus = ["N+1 detected: ", ' queries for table "', '" (via ', ".", ")"]
        dupe = ["Duplicate query: ", ' identical queries for table "', '"']
        grouped = group_by_trigger([nplus, dupe])
        line = 'WARNING: Duplicate query: 2 identical queries for table "app_book"'
        assert check_emitted_strings("docs/x.md", line, grouped) == []

    def test_a_genuinely_stale_line_is_still_reported(self) -> None:
        """Positive control: the tolerance above does not swallow real drift."""
        nplus = ["N+1 detected: ", ' queries for table "', '" (via ', ".", ")"]
        dupe = ["Duplicate query: ", ' identical queries for table "', '"']
        grouped = group_by_trigger([nplus, dupe])
        line = 'CRITICAL: N+1 detected: 12 queries for table "app_author" (field: author)'
        assert len(check_emitted_strings("docs/x.md", line, grouped)) == 1


class TestEncodingIsNotDrift:
    """SVG, HTML and JSON re-spell the quotes the templates contain."""

    SEGMENTS: ClassVar[list[str]] = ["Add .", "('", "') to your ", " queryset"]

    def test_html_entities_are_not_reported(self) -> None:
        """`&#x27;` is an apostrophe to the reader."""
        grouped = group_by_trigger([self.SEGMENTS])
        line = "<text>Add .select_related(&#x27;author&#x27;) to your Book queryset</text>"
        assert check_emitted_strings("examples/x.svg", line, grouped) == []

    def test_backslash_escaped_quotes_are_not_reported(self) -> None:
        """JSON values and Python literals escape the inner quotes."""
        segments = ['Missing index: column "', '" on ', ' (table "', '")']
        grouped = group_by_trigger([segments])
        line = (
            '  "description": "Missing index: column \\"title\\" on Book (table \\"app_book\\")",'
        )
        assert check_emitted_strings("examples/outputs/report.json", line, grouped) == []


class TestVersionCheck:
    """Check B, over synthetic inputs so it is pinned independently."""

    def test_bare_literal_after_an_echo_is_checked(self) -> None:
        """The installation.md shape: print __version__, then the value."""
        text = ">>> print(query_doctor.__version__)\n1.0.3\n"
        found = check_version_literals("docs/x.md", text, "2.3.0")
        assert len(found) == 1 and "1.0.3" in found[0]

    def test_a_matching_literal_passes(self) -> None:
        """Positive control for the same shape."""
        text = ">>> print(query_doctor.__version__)\n2.3.0\n"
        assert check_version_literals("docs/x.md", text, "2.3.0") == []

    def test_a_bare_version_with_no_echo_is_ignored(self) -> None:
        """A version in prose is not a claim about this package's output."""
        text = "Django 4.2 is supported.\n5.0.1\n"
        assert check_version_literals("docs/x.md", text, "2.3.0") == []

    def test_version_field_is_checked_anywhere(self) -> None:
        """The reporter emits this field, so any sample of it is a claim."""
        text = '{\n  "version": "2.1.0",\n}\n'
        found = check_version_literals("docs/x.md", text, "2.3.0")
        assert len(found) == 1 and "2.1.0" in found[0]
