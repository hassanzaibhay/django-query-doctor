"""Pins the SVG example line data to the real terminal captures.

``examples/generate_svgs.py`` carries terminal text hand-transcribed from
``examples/screenshots/*.capture.txt``, which ``scripts/regen_examples.py``
regenerates from real runs. Nothing enforced that the transcription matched,
so the shipped SVGs could drift silently from real output on any format change
(FOLLOWUPS entry 8).

Why containment and not equality: the captures cannot be compared verbatim.
They embed absolute machine paths, and ``auto_fix.capture.txt`` embeds a pytest
tmpdir whose counter changes on every run
(``...\\pytest-of-<user>\\pytest-46\\...``). The SVGs deliberately relabel those
to ``myapp/views.py`` and drop some lines for width. So the direction that
matters is checked instead: **every line the SVG shows must be traceable to a
capture line**. A capture line the SVG omits is fine; an SVG line the tool never
produced is not.

The generator is read with ``ast``, never imported: importing it would execute
its module-level ``create_terminal_svg`` calls and rewrite the shipped SVGs as a
side effect of running the tests.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "examples" / "generate_svgs.py"
SCREENSHOTS = REPO_ROOT / "examples" / "screenshots"

# Line prefixes whose *content* is presentation-substituted and cannot be
# content-matched, so only their presence is allowed rather than checked:
#   "Location:" - capture holds the absolute path of the regen script and the
#                 test function that ran it; the SVG relabels both to a
#                 plausible user file.
#   "--- ", "+++ " - unified-diff headers holding the pytest tmpdir path.
# "@@ " is deliberately NOT here: hunk headers are real tool output and are
# content-matched.
PRESENTATION_SUBSTITUTED = ("Location:", "--- ", "+++ ")

# Editorial lines written for the reader that are not tool output at all. Each
# needs its own justification; anything else added to an SVG must fail.
EDITORIAL_ANNOTATIONS: dict[str, set[str]] = {
    # Explains what the [MANUAL FIX ONLY] marker on the hunk above means. The
    # fixer prints the marker but never this gloss.
    "auto_fix.svg": {"([MANUAL FIX ONLY] fixes are shown here but refused by --apply)"},
}

# SVGs with no capture to pin against. regen_examples.py produces exactly two
# .capture.txt files, so these four are hand-authored end to end and this test
# cannot verify them. Listed by relpath so the gap is named and cannot grow
# silently: a new SVG added without a capture fails the guard below.
UNPINNED_SVGS = {
    "project_diagnosis.svg",
    "query_budget.svg",
    "quick_start.svg",
    "test_usage.svg",
}


def _svg_specs() -> dict[str, list[str]]:
    """Extract ``filename -> [line text]`` from the generator without importing it."""
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    specs: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "create_terminal_svg":
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            filename = ast.literal_eval(kwargs["filename"])
            lines = ast.literal_eval(kwargs["lines"])
            specs[filename] = [entry.get("text", "") for entry in lines]
    return specs


def _captures() -> dict[str, Path]:
    """Map ``<name>.svg`` to its ``<name>.capture.txt``."""
    return {p.name.replace(".capture.txt", ".svg"): p for p in SCREENSHOTS.glob("*.capture.txt")}


def _normalize(text: str) -> str:
    """Collapse whitespace so indentation choices do not count as drift."""
    return re.sub(r"\s+", " ", text.strip())


def _strip_trailing_comment(text: str) -> str:
    """Drop a trailing ``# ...`` annotation from a captured source line.

    The captures echo the sample's inline comments (``# N+1``); the SVGs show
    the code without them. Applied only when building the *allowed* set from
    the capture, never to the SVG line, so the SVG side stays strict.
    """
    return re.sub(r"\s+#\s.*$", "", text).strip()


class TestSVGLineDataMatchesCaptures:
    """Every line the shipped SVGs display must come from a real capture."""

    @pytest.mark.parametrize("svg_name", sorted(_captures()))
    def test_every_svg_line_traces_to_a_capture_line(self, svg_name: str) -> None:
        """No SVG may display text the captured run never produced."""
        capture = _captures()[svg_name]
        captured = {
            _normalize(line) for line in capture.read_text(encoding="utf-8").splitlines()
        } - {""}

        # Positive control: an empty capture would make every assertion below
        # vacuous, so a capture that reads as blank is itself a failure.
        assert len(captured) > 5, f"{capture.name} looks empty; the check would prove nothing"

        allowed = captured | {_strip_trailing_comment(line) for line in captured}
        annotations = EDITORIAL_ANNOTATIONS.get(svg_name, set())

        unmatched = [
            line
            for line in (_normalize(raw) for raw in _svg_specs()[svg_name])
            if line
            and not line.startswith(PRESENTATION_SUBSTITUTED)
            and line not in annotations
            and line not in allowed
        ]

        assert unmatched == [], (
            f"{svg_name} shows {len(unmatched)} line(s) with no source in "
            f"{capture.name}: {unmatched}"
        )

    def test_unpinned_svgs_are_exactly_the_declared_set(self) -> None:
        """A new SVG added without a capture must fail rather than go unchecked.

        Without this, the gap this test leaves would widen silently: the
        parametrization above only covers SVGs that happen to have a capture,
        so an unpinned addition would simply never be tested.
        """
        specs = _svg_specs()
        assert specs, "no create_terminal_svg calls found; the AST extraction broke"

        unpinned = set(specs) - set(_captures())
        assert unpinned == UNPINNED_SVGS, (
            "SVGs without a capture changed. Add a capture in "
            "scripts/regen_examples.py, or update UNPINNED_SVGS with a reason."
        )
