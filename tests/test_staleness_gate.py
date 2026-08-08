"""Tests for the anti-staleness gate.

The load-bearing one is :meth:`TestGateCatchesTheDefectsThatMotivatedIt`.
A gate that cannot catch the defects it was built for is theatre, and the
only way to know is to point it at the revision that carried them.
"""

from __future__ import annotations

import os
import subprocess
from typing import ClassVar

import pytest

from scripts.staleness_gate import (
    SELF,
    check_emitted_strings,
    check_version_literals,
    group_by_trigger,
    in_scope,
    line_matches_template,
    sweep,
    tracked_files,
    trigger_of,
    unexplained_triggers,
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


def should_skip_history(rev_present: bool, in_ci: bool) -> bool:
    """Decide whether to skip the acceptance criterion, given clone and env.

    A shallow local clone is a legitimate reason to skip -- a contributor
    running ``pytest`` after ``git clone --depth 1`` has no 96cee41 to point
    at. CI is not: there the checkout is ours to configure, so a missing
    revision means the ``fetch-depth: 0`` this file depends on was lost, and
    skipping would report that regression as green. A skip is a zero, so under
    ``CI`` the criterion runs and fails loudly instead.

    Args:
        rev_present: Whether ``DEFECTIVE_REV`` is in this clone.
        in_ci: Whether the ``CI`` environment variable is set.

    Returns:
        True if the acceptance criterion should be skipped.
    """
    return not rev_present and not in_ci


_IN_CI = bool(os.environ.get("CI"))

needs_history = pytest.mark.skipif(
    should_skip_history(_rev_exists(), _IN_CI),
    reason=f"{DEFECTIVE_REV} not present (shallow clone, local run)",
)


class TestGateIsCleanAtHead:
    """The gate must pass on the tree it ships with."""

    def test_no_violations_at_head(self) -> None:
        """A gate that is red on its own tree gets disabled, not fixed."""
        assert sweep() == []

    def test_the_gate_scans_its_own_directory(self) -> None:
        """`scripts/` must stay in scope: the defect that motivated it lived there."""
        assert in_scope("scripts/regen_examples.py")

    def test_the_gate_scans_itself(self) -> None:
        """No self-exemption. The module is a document like any other."""
        assert in_scope(SELF)

    def test_the_gate_module_is_tracked(self) -> None:
        """The scan must be reading the tree being committed.

        `tracked_files` shells `git ls-files`, so an untracked file is
        invisible to the gate -- including the gate itself. This actually
        happened: the gate reported clean in the commit that introduced it,
        purely because its own file was not yet staged, and only started
        reporting on itself once committed. A clean run made before the file
        under test is tracked says nothing.

        `dash_gate.tracked_files` has the identical property, so this is a
        class rather than an instance. It is bounded in practice -- pre-commit
        runs against the index and CI checks out a fully tracked tree -- but
        the local failure mode is a gate reporting on a different tree than
        the one being committed.
        """
        assert SELF in tracked_files()

    def test_every_scanned_file_is_tracked(self) -> None:
        """Generalises the above: the scan's input is exactly the tracked set."""
        scanned = [p for p in tracked_files() if in_scope(p)]
        assert scanned, "nothing in scope; the check would prove nothing"
        assert set(scanned) <= set(tracked_files())

    def test_only_the_allowlist_literal_is_skipped_in_self(self) -> None:
        """The span skip must cover the entries and nothing beyond them.

        Allowlisting a line means writing it out again, so the entry quotes
        the string it excuses. Skipping the literal's span resolves that;
        skipping more would blind the module to its own prose.
        """
        from pathlib import Path

        from scripts.staleness_gate import allowlist_line_span

        text = Path(SELF).read_text(encoding="utf-8")
        span = allowlist_line_span(text)
        lines = text.splitlines()

        assert span, "the ALLOWLIST literal was not located"
        assert lines[min(span) - 1].startswith("ALLOWLIST"), lines[min(span) - 1]
        assert lines[max(span) - 1].strip() == "}", lines[max(span) - 1]
        # The module docstring sits above it and stays in the scan.
        assert 1 not in span


class TestTheHistoryGuardRunsWhereItMatters:
    """The acceptance criterion below must not be skippable in CI.

    It was: the ``test`` job's checkout took the default ``fetch-depth: 1``,
    96cee41 was absent in all 18 cells, and every test in the class below
    skipped while the job reported success. The guard is exercised directly
    rather than through the environment so both arms are asserted.
    """

    def test_ci_never_skips(self) -> None:
        """A missing revision under CI is a checkout regression, not a skip."""
        assert should_skip_history(rev_present=False, in_ci=True) is False

    def test_a_shallow_local_clone_still_skips(self) -> None:
        """Off CI a shallow clone is legitimate and must not fail the suite."""
        assert should_skip_history(rev_present=False, in_ci=False) is True

    def test_a_present_revision_never_skips(self) -> None:
        """Positive control: with history available the criterion always runs."""
        assert should_skip_history(rev_present=True, in_ci=False) is False
        assert should_skip_history(rev_present=True, in_ci=True) is False


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
        assert _rev_exists(), (
            f"{DEFECTIVE_REV} is absent from this clone, so the acceptance "
            "criterion cannot run. Reached under CI this means the `test` job's "
            "checkout lost its `fetch-depth: 0` (.github/workflows/ci.yml)."
        )
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


class TestTwoQuotationsOnOneLineAreJudgedApart:
    """A healthy clause must not vouch for a stale one beside it.

    ``nplusone.py:356-358`` builds one prescription by concatenating two
    f-strings, so a document line quoting it carries two triggers at disjoint
    offsets. Accepting the line because *some* template matched let the
    healthy tail clear the stale head, and the sentence break inside the
    borrowed gap is what tells the two apart. Both defects met at
    ``docs/examples/index.md:30``.
    """

    FIX: ClassVar[list[str]] = ["Add .", "('", "') to your ", " queryset"]
    TAIL: ClassVar[list[str]] = [". For advanced filtering, use Prefetch('", "', queryset=...)"]

    # The exact bytes of docs/examples/index.md:30 at 96cee41: the fix clause
    # is stale (no model name), the Prefetch tail is current.
    STALE = (
        "   Fix: Add .prefetch_related('orderitem') to your queryset. "
        "For advanced filtering, use Prefetch('orderitem', queryset=...)"
    )
    # The same line as src/ emits it today.
    CURRENT = (
        "   Fix: Add .prefetch_related('orderitem') to your Order queryset. "
        "For advanced filtering, use Prefetch('orderitem', queryset=...)"
    )

    @property
    def grouped(self) -> dict[str, list[list[str]]]:
        """The two templates, grouped as the gate groups them."""
        return group_by_trigger([self.FIX, self.TAIL])

    def test_the_stale_line_is_reported(self) -> None:
        """End to end, on the line that motivated the rule."""
        found = check_emitted_strings("docs/x.md", self.STALE, self.grouped)
        assert len(found) == 1, found

    def test_the_current_line_is_clean(self) -> None:
        """Positive control: the same two clauses, both current, pass."""
        assert check_emitted_strings("docs/x.md", self.CURRENT, self.grouped) == []

    def test_only_the_stale_clauses_trigger_is_unexplained(self) -> None:
        """The tail matches, so it explains itself and nothing else."""
        unexplained = unexplained_triggers(self.STALE, self.grouped)
        assert [t for _, t in unexplained] == ["') to your "], unexplained

    def test_the_borrowed_segment_is_denied_by_the_sentence_break(self) -> None:
        """The mechanism, isolated: the gap spans a clause boundary."""
        assert not line_matches_template(self.STALE, self.FIX)
        assert line_matches_template(self.CURRENT, self.FIX)

    def test_a_value_with_a_comma_is_still_a_value(self) -> None:
        """Only a sentence break disqualifies a gap, not any punctuation."""
        segments = ["Use .defer(", ") to skip loading large fields"]
        assert line_matches_template(
            "Use .defer('description', 'body') to skip loading large fields", segments
        )

    def test_overlapping_triggers_are_still_pooled(self) -> None:
        """Substring triggers are competing readings of one span, not two.

        Regression guard for the 8 false positives that motivated pooling.
        """
        nplus = ["N+1 detected: ", ' queries for table "', '"']
        dupe = ["Duplicate: ", ' identical queries for table "', '"']
        grouped = group_by_trigger([nplus, dupe])
        line = 'Duplicate: 4 identical queries for table "testapp_book"'
        assert unexplained_triggers(line, grouped) == []
        assert check_emitted_strings("docs/x.md", line, grouped) == []

    def test_one_template_spanning_two_triggers_explains_both(self) -> None:
        """The fat-SELECT shape: a longer form contains the shorter's trigger.

        `fat_select.py:236` and `:245` emit two forms whose triggers land at
        disjoint offsets on the same line. The longer form's span covers both,
        so a line matching it is clean -- the case a window-per-trigger rule
        got wrong.
        """
        short = ["Fat SELECT: ", ' columns from "', '"']
        long_ = ["Fat SELECT: ", ' columns from "', '" including large fields: ']
        grouped = group_by_trigger([short, long_])
        line = (
            'INFO: Fat SELECT: 8 columns from "testapp_book" including large fields: description'
        )
        assert unexplained_triggers(line, grouped) == []


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
