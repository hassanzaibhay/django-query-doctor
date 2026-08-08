"""Pins the SVG example line data to the real terminal captures.

``examples/generate_svgs.py`` carries terminal text hand-transcribed from
``examples/screenshots/*.capture.txt``, which ``scripts/regen_examples.py``
regenerates from real runs. Nothing enforced that the transcription matched,
so the shipped SVGs could drift silently from real output on any format change
(FOLLOWUPS entry 8).

Why containment and not equality: the captures still cannot be compared
verbatim. They carry the callsite of the regeneration script rather than of a
user's view, and the SVGs deliberately relabel that to ``myapp/views.py`` and
drop some lines for width. So the direction that matters is checked instead:
**every line the SVG shows must be traceable to a capture line**. A capture
line the SVG omits is fine; an SVG line the tool never produced is not.

Until entry 44 the captures also embedded absolute machine paths and a pytest
tmpdir whose counter changed on every run, which was a second, independent
reason equality was impossible -- and, because these artifacts ship inside the
sdist, a published leak. ``scripts/regen_examples.py`` now normalizes both:
the repository root becomes a repo-relative path and the fixture directory
becomes ``<tmpdir>``. ``TestGeneratedArtifactsCarryNoLocalPaths`` below keeps
it that way, and the staleness check that entry 59 asked for is possible only
because of it.

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

# Captures that pin something other than an SVG, so they have no ``<name>.svg``
# and must be excluded from the SVG parametrization rather than KeyError-ing.
# Declared, not inferred, so a capture that loses its consumer is noticed.
CAPTURES_WITHOUT_SVG = {
    # Pins the README's "See It in Action" block; checked by
    # TestReadmeBlockMatchesCapture below rather than by an SVG.
    "readme_console.svg",
}

# SVGs with no capture to pin against. These four are hand-authored end to end
# and this test cannot verify them. Listed by relpath so the gap is named and
# cannot grow silently: a new SVG added without a capture fails the guard below.
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
    """Map ``<name>.svg`` to its ``<name>.capture.txt``, SVG-backed ones only."""
    found = {p.name.replace(".capture.txt", ".svg"): p for p in SCREENSHOTS.glob("*.capture.txt")}
    return {name: path for name, path in found.items() if name not in CAPTURES_WITHOUT_SVG}


def _all_captures() -> dict[str, Path]:
    """Every capture, including those with no SVG consumer."""
    return {p.name.replace(".capture.txt", ".svg"): p for p in SCREENSHOTS.glob("*.capture.txt")}


# Durations differ on every run, so an exact diff of a regenerated capture
# would be permanently red. Masking them leaves everything that actually
# indicates drift: the wording, the counts, the callsites, the ordering.
_VOLATILE_RE = re.compile(r"\d+\.\d+ *ms")


def _normalize(text: str) -> str:
    """Collapse whitespace so indentation choices do not count as drift.

    Durations are masked for the same reason ``_stable`` masks them below:
    they differ on every run, so an unmasked comparison would turn red
    whenever the captures are regenerated, for a reason that says nothing
    about correctness. The wording, counts, callsites and ordering are all
    still content-matched.
    """
    return _VOLATILE_RE.sub("<ms>", re.sub(r"\s+", " ", text.strip()))


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

    def test_captures_without_an_svg_are_exactly_the_declared_set(self) -> None:
        """A capture whose consumer disappears must be noticed, not skipped.

        ``_captures`` filters these out so the parametrization above does not
        look for an SVG that was never meant to exist. Without this guard the
        filter would also silently swallow a capture whose SVG was deleted.
        """
        orphans = set(_all_captures()) - set(_svg_specs())
        assert orphans == CAPTURES_WITHOUT_SVG, (
            "Captures without an SVG changed. Either the capture has a new "
            "consumer, or CAPTURES_WITHOUT_SVG needs updating with a reason."
        )


README = REPO_ROOT / "README.md"


def _readme_console_block() -> list[str]:
    """Return the lines of the README's console-output fenced block.

    Located by content rather than by line number so the test survives edits
    above it. Exactly one fenced block may contain the report banner.
    """
    lines = README.read_text(encoding="utf-8").splitlines()
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
            continue
        if current is not None:
            current.append(line)
    matching = [b for b in blocks if any(line.strip() == "Query Doctor Report" for line in b)]
    assert len(matching) == 1, (
        f"expected exactly one console block in README.md, got {len(matching)}"
    )
    return matching[0]


class TestReadmeBlockMatchesCapture:
    """The README's headline output block must be real tool output.

    This is the check that was missing when 2.3.0 changed the N+1 wording:
    the block kept printing ``(field: author)`` and ``to your queryset``,
    neither of which the analyzer can emit, on the first page a reader opens.
    """

    def test_every_readme_console_line_traces_to_the_capture(self) -> None:
        """No line of the README block may be text the tool never produced."""
        capture = SCREENSHOTS / "readme_console.capture.txt"
        captured = {
            _normalize(line) for line in capture.read_text(encoding="utf-8").splitlines()
        } - {""}

        # Positive control: an empty capture would make the assertion vacuous.
        assert len(captured) > 5, f"{capture.name} looks empty; the check would prove nothing"

        allowed = captured | {_strip_trailing_comment(line) for line in captured}
        unmatched = [
            line
            for line in (_normalize(raw) for raw in _readme_console_block())
            if line and not line.startswith(PRESENTATION_SUBSTITUTED) and line not in allowed
        ]

        assert unmatched == [], (
            f"README.md shows {len(unmatched)} console line(s) with no source in "
            f"{capture.name}: {unmatched}"
        )

    def test_readme_block_carries_the_ordering_note(self) -> None:
        """The note is the third thing 2.3.0 changed and the README dropped.

        Guards the two lines above from passing on a block that simply
        omits output: containment cannot catch a missing line.
        """
        block = " ".join(_readme_console_block())
        assert "findings are listed in the order to apply them" in block


OUTPUTS = REPO_ROOT / "examples" / "outputs"

# Every spelling of a local absolute path these artifacts have carried, raw
# and JSON-escaped. A single-backslash pattern missed an entire file when this
# defect was first measured, so both are checked.
LOCAL_PATH_MARKERS = (
    r"C:\Users",
    r"C:\\Users",
    "C:/Users",
    "pytest-of-",
    str(REPO_ROOT),
)


def _stable(text: str) -> str:
    """Mask the fields that legitimately differ between two runs."""
    return _VOLATILE_RE.sub("<ms>", text)


class TestGeneratedArtifactsCarryNoLocalPaths:
    """Entry 44: these files ship in the sdist, so an absolute path is published.

    ``examples/outputs/report.{html,json}`` were never covered by any sync
    test at all, and both carried the author's home directory. The published
    2.2.0 sdist keeps them permanently -- PyPI artifacts are immutable -- so
    this guard is about every release after it.
    """

    @pytest.mark.parametrize(
        "relpath",
        [
            "examples/outputs/report.html",
            "examples/outputs/report.json",
            "examples/outputs/query_budget_output.txt",
            "examples/screenshots/console_output.capture.txt",
            "examples/screenshots/auto_fix.capture.txt",
        ],
    )
    def test_artifact_has_no_absolute_local_path(self, relpath: str) -> None:
        """No generated artifact may name a directory on the author's machine."""
        text = (REPO_ROOT / relpath).read_text(encoding="utf-8")
        assert text.strip(), f"{relpath} is empty; the check would prove nothing"
        found = [marker for marker in LOCAL_PATH_MARKERS if marker in text]
        assert found == [], f"{relpath} carries {found}"

    def test_report_json_locations_are_repo_relative(self) -> None:
        """Positive control: the callsites are present, and they are relative."""
        import json

        data = json.loads((OUTPUTS / "report.json").read_text(encoding="utf-8"))
        files = [rx["location"]["file"] for rx in data["prescriptions"] if rx.get("location")]
        assert files, "positive control: the report must carry callsites at all"
        for path in files:
            assert not path.startswith("/"), path
            assert ":" not in path, f"{path} looks like a Windows absolute path"

    def test_report_html_and_json_describe_the_same_run(self) -> None:
        """The two artifacts are rendered from one report and must agree.

        Neither had any sync test, so they could drift apart -- or one could be
        regenerated without the other -- with nothing to notice.
        """
        import json

        data = json.loads((OUTPUTS / "report.json").read_text(encoding="utf-8"))
        html = (OUTPUTS / "report.html").read_text(encoding="utf-8")
        assert data["prescriptions"], "positive control: the run must have findings"
        for rx in data["prescriptions"]:
            marker = rx["description"].split(":")[0]
            assert marker in html, f"{marker!r} is in report.json but not report.html"


class TestCapturesAreNotStale:
    """Entry 59: nothing compared a committed capture against a fresh run.

    A capture could drift from current output indefinitely -- which is exactly
    what happened to the console capture when the N+1 prescription wording
    changed. Regenerating into a temporary directory and diffing catches it at
    the source rather than one step downstream at the SVG.
    """

    @pytest.mark.django_db
    def test_console_capture_matches_a_fresh_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regenerate the console capture into a temp dir and diff it."""
        from scripts import regen_examples

        monkeypatch.setattr(regen_examples, "SCREENSHOTS", tmp_path)
        regen_examples.test_capture_console_output()

        fresh = (tmp_path / "console_output.capture.txt").read_text(encoding="utf-8")
        committed = (SCREENSHOTS / "console_output.capture.txt").read_text(encoding="utf-8")
        assert _stable(fresh) == _stable(committed), (
            "examples/screenshots/console_output.capture.txt is stale. "
            "Re-run: pytest scripts/regen_examples.py -c pyproject.toml -q -s"
        )

    @pytest.mark.django_db
    def test_readme_capture_matches_a_fresh_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same for the README capture, which the README block is pasted from."""
        from scripts import regen_examples

        monkeypatch.setattr(regen_examples, "SCREENSHOTS", tmp_path)
        regen_examples.test_capture_readme_console_output()

        fresh = (tmp_path / "readme_console.capture.txt").read_text(encoding="utf-8")
        committed = (SCREENSHOTS / "readme_console.capture.txt").read_text(encoding="utf-8")
        assert _stable(fresh) == _stable(committed), (
            "examples/screenshots/readme_console.capture.txt is stale. "
            "Re-run: pytest scripts/regen_examples.py -c pyproject.toml -q -s"
        )

    @pytest.mark.django_db
    def test_auto_fix_capture_matches_a_fresh_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same for the fixer dry-run capture, whose tmpdir is now normalized.

        Needs the database: the capture is built from a real analyzer run,
        not from hand-written prescriptions.
        """
        from scripts import regen_examples

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.setattr(regen_examples, "SCREENSHOTS", out_dir)
        regen_examples.test_capture_fix_queries_dry_run(work)

        fresh = (out_dir / "auto_fix.capture.txt").read_text(encoding="utf-8")
        committed = (SCREENSHOTS / "auto_fix.capture.txt").read_text(encoding="utf-8")
        assert _stable(fresh) == _stable(committed), (
            "examples/screenshots/auto_fix.capture.txt is stale. "
            "Re-run: pytest scripts/regen_examples.py -c pyproject.toml -q -s"
        )
