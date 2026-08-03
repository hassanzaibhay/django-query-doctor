"""Pin every prescription description the suite emits, and diff it on change.

``baseline.py`` keys a stored issue on ``analyzer:file_path:message``, falling
back to ``description`` -- see ``BaselineManager._issue_key``. So a reworded
description silently rekeys every entry a user has already accepted, and their
baseline stops suppressing what it used to. 2.3.0 shipped exactly that and
``UPGRADING.md`` had to disclose it after the fact.

Byte-equality of the whole corpus is the wrong assertion: a change that fixes a
false positive *should* remove strings, and a change that adds a fixture
*should* add them. What must not happen is an unreviewed one. So the corpus is
stored as a file and the delta is declared here, in both directions:

    after  - before  must be a subset of ADDED
    before - after   must be a subset of REMOVED

Both lists are literal, so approving this file is approving the exact
behavioural delta. Refresh ``tests/data/emitted_descriptions.txt`` and empty
the lists once a change has landed and been reviewed.

The corpus comes from a full run rather than a hand-picked fixture set, so a
description added by any analyzer is covered, not just the one under change.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

CORPUS = pathlib.Path(__file__).parent / "data" / "emitted_descriptions.txt"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Descriptions this branch introduces.
ADDED: list[str] = [
    # Positive control for the deep-chain site's relation-kind guard, which
    # needs a ModelSerializer to have a field kind to check.
    "Possible N+1 in S.get_n(): 'obj.author.name' may trigger a query per object "
    "if 'author' is not select_related",
    # Not from an analyzer change: `Book.tags` was added to `tests/testapp`
    # (CLAUDE.md specifies it and the model was missing), so Book's cascade
    # set grew a through table and the write analyzer now sees it.
    'Write N+1 detected: 4 single-row DELETE statements for table "testapp_book_tags". '
    "One bulk statement replaces all 4.",
    # Ten from the positive-control arms of
    # TestEveryPrefetchSiteRoutesThroughTheRelationGuard, five per fixture:
    # `Relation` is a ModelSerializer over a declared reverse FK, `SetSuffix`
    # a plain Serializer relying on the `_set` arm. Five and not four because
    # sites 3 and 5 iterate `obj.<attr>.all()`, and `_check_call` (site 1)
    # matches that call too -- so the `.all()` form fires site 1 a second time
    # alongside the `.count()` form.
    "N+1 risk in Relation.get_n(): 'obj.items.all()' triggers a query per object",
    "N+1 risk in Relation.get_n(): 'obj.items.count()' triggers a query per object",
    "N+1 risk in Relation.get_n(): comprehension over 'obj.items' may trigger a query per object",
    "N+1 risk in Relation.get_n(): comprehension over 'obj.items.all()' "
    "triggers a query per object",
    "N+1 risk in Relation.get_n(): loop over 'obj.items.all()' triggers a query per object",
    "N+1 risk in SetSuffix.get_n(): 'obj.thing_set.all()' triggers a query per object",
    "N+1 risk in SetSuffix.get_n(): 'obj.thing_set.count()' triggers a query per object",
    "N+1 risk in SetSuffix.get_n(): comprehension over 'obj.thing_set' "
    "may trigger a query per object",
    "N+1 risk in SetSuffix.get_n(): comprehension over 'obj.thing_set.all()' "
    "triggers a query per object",
    "N+1 risk in SetSuffix.get_n(): loop over 'obj.thing_set.all()' triggers a query per object",
    # Three from TestASuppressedGeneratorDoesNotSilenceTheOnesAfterIt, whose
    # two fixtures are both named `S`: the surviving second generator at sites
    # 5 and 6, plus site 1 matching the same `obj.items.all()` call.
    "N+1 risk in S.get_n(): 'obj.items.all()' triggers a query per object",
    "N+1 risk in S.get_n(): comprehension over 'obj.items' may trigger a query per object",
    "N+1 risk in S.get_n(): comprehension over 'obj.items.all()' triggers a query per object",
]

# Descriptions this branch stops emitting.
#
# Empty, and that is a claim about fixtures rather than about the guards. All
# seven sites now resolve before naming a relation, which suppresses every
# fixture reading `obj.items` or `obj.tags` off a plain Serializer: 19
# descriptions across 14 fixture classes when first measured. Rather than let
# that coverage vanish, all 14 classes were converted to ModelSerializers over
# models that declare those attributes, keeping their class names, field names
# and method bodies. Descriptions interpolate exactly those, so they survive
# byte for byte. See TestEveryPrefetchSiteRoutesThroughTheRelationGuard for the
# suppression each site now performs, proven by mutation rather than inferred
# from this list.
REMOVED: list[str] = []


def _record_corpus(destination: pathlib.Path) -> None:
    """Run the suite in a subprocess with the recorder plugin attached."""
    env = {
        **os.environ,
        "QD_DESCRIPTION_OUT": str(destination),
        # Read by this module to skip itself in the inner run. Without it the
        # subprocess spawns a subprocess.
        "QD_DESCRIPTION_RECORDING": "1",
    }
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "tests.description_recorder",
            "-p",
            "no:cacheprovider",
            "--no-cov",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if not destination.exists():
        pytest.fail(f"the recorder wrote nothing.\n{done.stdout[-4000:]}")


@pytest.mark.skipif(
    os.environ.get("QD_DESCRIPTION_RECORDING") == "1",
    reason="inner recording run; spawning another would not terminate",
)
class TestEmittedDescriptionsMatchTheReviewedCorpus:
    """The corpus is data under review, not an incidental artifact."""

    @pytest.fixture(scope="class")
    @classmethod
    def emitted(cls, tmp_path_factory: pytest.TempPathFactory) -> list[str]:
        """Every description a full run constructs, sorted and deduplicated."""
        out = tmp_path_factory.mktemp("corpus") / "emitted.txt"
        _record_corpus(out)
        return out.read_text(encoding="utf-8").splitlines()

    @pytest.fixture(scope="class")
    @classmethod
    def stored(cls) -> list[str]:
        """The reviewed corpus checked into the tree."""
        return CORPUS.read_text(encoding="utf-8").splitlines()

    def test_the_corpus_is_not_empty(self, emitted: list[str]) -> None:
        """Guard: an empty run would satisfy every subset assertion below."""
        assert len(emitted) > 100, len(emitted)

    def test_nothing_was_added_without_being_declared(
        self, emitted: list[str], stored: list[str]
    ) -> None:
        """`after - before` must be covered by ADDED."""
        added = sorted(set(emitted) - set(stored))
        assert set(added) <= set(ADDED), [a for a in added if a not in ADDED]

    def test_nothing_vanished_without_being_declared(
        self, emitted: list[str], stored: list[str]
    ) -> None:
        """`before - after` must be covered by REMOVED.

        This is the direction that costs users their baselines: a description
        that disappears takes its key with it.
        """
        removed = sorted(set(stored) - set(emitted))
        assert set(removed) <= set(REMOVED), [r for r in removed if r not in REMOVED]

    def test_the_declared_delta_is_not_stale(self, emitted: list[str], stored: list[str]) -> None:
        """A declared entry that no longer applies is an unreviewed change too.

        Without this, ADDED and REMOVED accumulate entries that excuse
        whatever drifts into them next.
        """
        assert set(ADDED) <= set(emitted), sorted(set(ADDED) - set(emitted))
        assert set(REMOVED) <= set(stored), sorted(set(REMOVED) - set(stored))
        assert set(ADDED).isdisjoint(stored), sorted(set(ADDED) & set(stored))
        assert set(REMOVED).isdisjoint(emitted), sorted(set(REMOVED) & set(emitted))

    def test_the_corpus_is_sorted_and_deduplicated(self, stored: list[str]) -> None:
        """A file that is not canonical produces diffs nobody can read."""
        assert stored == sorted(set(stored))
