"""Regenerate examples/outputs/* and the SVG content captures from real runs.

This is the audit trail for the example artifacts: everything under
``examples/outputs/`` and the terminal text rendered into
``examples/screenshots/console_output.svg`` / ``auto_fix.svg`` (via
``examples/generate_svgs.py``) is produced by THIS script running the
actual tool - never hand-written.

Regenerates:
- examples/outputs/report.json          (JSONReporter, real diagnose_queries run)
- examples/outputs/report.html          (HTMLReporter, same run)
- examples/outputs/query_budget_output.txt  (@query_budget result)
- examples/screenshots/console_output.capture.txt  (ConsoleReporter plain render)
- examples/screenshots/readme_console.capture.txt  (the README "See It in Action" block)
- examples/screenshots/auto_fix.capture.txt        (QueryFixer dry-run diff)

The two ``.capture.txt`` files are the source text for the SVG line data in
``examples/generate_svgs.py`` - transcribe verbatim, except file paths, which
are relabeled to ``myapp/views.py`` for readability (the only deliberate
divergence). After updating the line data, re-render with:

    cd examples && python generate_svgs.py

Run (from the repo root; deliberately NOT auto-collected by plain ``pytest``
because the filename does not match ``test_*.py``):

    python -m pytest scripts/regen_examples.py -c pyproject.toml -q -s

All outputs must be valid UTF-8; strings the tool emits are pure ASCII.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = REPO_ROOT / "examples" / "outputs"
SCREENSHOTS = REPO_ROOT / "examples" / "screenshots"

# Placeholder for the pytest fixture directory. Its counter (pytest-<n>) and
# the Windows account display name inside it both change between runs, so the
# whole prefix is replaced rather than pinned.
TMPDIR_PLACEHOLDER = "<tmpdir>"

# NUL cannot appear in any artifact, so it is safe as an internal marker.
_ROOT_MARK = "\x00root\x00"
_TMP_MARK = "\x00tmp\x00"
_MARKED_PATH_RE = re.compile(r"(\x00(?:root|tmp)\x00)([^\s\"']*)")


def _path_forms(base: Path) -> list[str]:
    """Every spelling of ``base`` that can appear inside a generated artifact.

    Three of them, and missing any one leaves a leak behind: the native
    Windows form, the forward-slash form, and the JSON-escaped form that
    ``json.dumps`` produces for a value containing backslashes. The first
    audit of this defect used a single-backslash pattern and missed an entire
    file for exactly that reason.

    Args:
        base: An absolute directory to build spellings for.

    Returns:
        The spellings, longest first so no prefix shadows a longer match.
    """
    native = str(base)
    forms = {native, native.replace("\\", "/"), native.replace("\\", "\\\\")}
    return sorted(forms, key=len, reverse=True)


def normalize_paths(text: str, tmp_dir: Path | None = None) -> str:
    """Replace machine-specific absolute paths with stable, portable ones.

    These artifacts are committed and ship inside the sdist, so an absolute
    path in one is published. The repository root becomes a repo-relative
    path with forward slashes; a pytest fixture directory becomes
    ``<tmpdir>``.

    Args:
        text: The rendered artifact.
        tmp_dir: The pytest fixture directory used by this run, if any.

    Returns:
        The text with every machine-specific prefix replaced.
    """
    for form in _path_forms(REPO_ROOT):
        text = text.replace(form, _ROOT_MARK)
    if tmp_dir is not None:
        for form in _path_forms(tmp_dir):
            text = text.replace(form, _TMP_MARK)

    def _rewrite(match: re.Match[str]) -> str:
        prefix = TMPDIR_PLACEHOLDER if match.group(1) == _TMP_MARK else ""
        tail = match.group(2).replace("\\\\", "/").replace("\\", "/").lstrip("/")
        return f"{prefix}/{tail}" if prefix else tail

    return _MARKED_PATH_RE.sub(_rewrite, text)


def _write(path: Path, text: str, tmp_dir: Path | None = None) -> None:
    """Normalize paths, assert none leaked, and write the artifact.

    Args:
        path: Destination file.
        text: The rendered artifact.
        tmp_dir: The pytest fixture directory used by this run, if any.
    """
    normalized = normalize_paths(text, tmp_dir)
    for leak in ("C:\\Users", "C:/Users", "pytest-of-"):
        assert leak not in normalized, f"{path.name} still carries {leak!r}"
    path.write_text(normalized, encoding="utf-8")


@pytest.mark.django_db
def test_regenerate_outputs() -> None:
    """Regenerate report.json, report.html, and query_budget_output.txt."""
    from tests.factories import AuthorFactory, BookFactory, PublisherFactory, ReviewFactory

    from query_doctor.context_managers import diagnose_queries
    from query_doctor.decorators import query_budget
    from query_doctor.exceptions import QueryBudgetError
    from query_doctor.reporters.html_reporter import HTMLReporter
    from query_doctor.reporters.json_reporter import JSONReporter

    # Seed a workload rich enough to trigger several analyzer categories
    for _ in range(20):
        book = BookFactory(author=AuthorFactory(), publisher=PublisherFactory())
        ReviewFactory(book=book)
        ReviewFactory(book=book)

    from tests.testapp.models import Book

    with diagnose_queries() as report:
        books = list(Book.objects.all())
        for b in books:
            _ = b.author.name  # N+1 on author
            _ = b.publisher.name  # N+1 on publisher
        # duplicate queries
        Book.objects.filter(title=books[0].title).count()
        Book.objects.filter(title=books[0].title).count()

    assert report.issues > 0  # positive control

    json_text = JSONReporter().render(report)
    _write(
        OUTPUTS / "report.json",
        json.dumps(json.loads(json_text), indent=2, default=str),
    )
    _write(OUTPUTS / "report.html", HTMLReporter().render(report))

    @query_budget(max_queries=5)
    def budget_limited_view() -> None:
        book_list = list(Book.objects.all())
        for b in book_list:
            _ = b.author.name  # exceeds budget

    try:
        budget_limited_view()
        budget_text = "Budget: PASSED (unexpected)"
    except QueryBudgetError as e:
        budget_text = f"Budget: EXCEEDED - {e}"

    _write(
        OUTPUTS / "query_budget_output.txt",
        "=" * 60 + "\n"
        "Query Doctor - Query Budget Example\n" + "=" * 60 + "\n\n"
        "@query_budget(max_queries=5)\n"
        "def budget_limited_view():\n"
        "    books = list(Book.objects.all())\n"
        "    for b in books:\n"
        "        _ = b.author.name  # N+1 - exceeds budget\n\n"
        f"Result: {budget_text}\n",
    )


@pytest.mark.django_db
def test_capture_console_output() -> None:
    """Capture the real plain console render for console_output.svg."""
    from tests.factories import AuthorFactory, BookFactory

    from query_doctor.context_managers import diagnose_queries
    from query_doctor.reporters.console import ConsoleReporter

    for _ in range(12):
        BookFactory(author=AuthorFactory())

    from tests.testapp.models import Book

    with diagnose_queries() as report:
        books = list(Book.objects.all())
        for book in books:
            _ = book.author.name  # N+1
        Book.objects.filter(title=books[0].title).count()  # duplicate x2
        Book.objects.filter(title=books[0].title).count()

    assert report.issues >= 3  # positive control
    output = ConsoleReporter()._render_plain(report)
    output.encode("ascii")  # SVG source text must stay ASCII
    _write(SCREENSHOTS / "console_output.capture.txt", output)


@pytest.mark.django_db
def test_capture_readme_console_output() -> None:
    """Capture the console render used by the README's "See It in Action" block.

    Shaped to produce exactly one N+1 and one fat SELECT so that
    ``ConsoleReporter._ordering_note`` fires: the note only appears when a
    report carries both, and the README block is the one place it is quoted.
    """
    from tests.factories import AuthorFactory, BookFactory

    from query_doctor.context_managers import diagnose_queries
    from query_doctor.reporters.console import ConsoleReporter
    from query_doctor.types import IssueType

    for _ in range(12):
        BookFactory(author=AuthorFactory())

    from tests.testapp.models import Book

    with diagnose_queries() as report:
        books = list(Book.objects.all())
        for book in books:
            _ = book.author.name  # N+1 on author; the base query is the fat SELECT

    kinds = {p.issue_type for p in report.prescriptions}
    # Positive control for the ordering note: it renders only when both are present.
    assert IssueType.N_PLUS_ONE in kinds, kinds
    assert IssueType.FAT_SELECT in kinds, kinds

    output = ConsoleReporter()._render_plain(report)
    output.encode("ascii")  # README block must stay ASCII
    _write(SCREENSHOTS / "readme_console.capture.txt", output)


@pytest.mark.django_db
def test_capture_fix_queries_dry_run(tmp_path: Path) -> None:
    """Capture a real QueryFixer dry-run diff for auto_fix.svg.

    Exactly what fix_queries prints on the dry-run path, including the
    [MANUAL FIX ONLY] tag on the N+1 hunk that --apply refuses to write.

    The prescriptions are produced by a real analyzer run and only their
    *callsite* is retargeted onto the synthetic ``views.py`` -- the fixer
    needs line numbers inside a file it can diff, which a live run cannot
    supply. Retargeting the callsite is the same deliberate divergence the
    module docstring already allows for paths; the description and fix text
    are never authored here. They were, once: hardcoded literals kept
    reproducing the pre-2.3.0 N+1 wording after the analyzer stopped emitting
    it, and the staleness check could not see it because the generator and the
    artifact agreed with each other.
    """
    import dataclasses

    from tests.factories import AuthorFactory, BookFactory

    from query_doctor.context_managers import diagnose_queries
    from query_doctor.fixer import QueryFixer
    from query_doctor.types import CallSite, IssueType, Prescription

    source = tmp_path / "views.py"
    source.write_text(
        "def book_list(request):\n"
        "    books = Book.objects.all()\n"
        "    for book in books:\n"
        "        _ = book.author.name\n"
        "    total = len(books)\n"
        "    recent = Book.objects.filter(published_date__gte=cutoff)\n",
        encoding="utf-8",
    )

    for _ in range(12):
        BookFactory(author=AuthorFactory())

    from tests.testapp.models import Book

    with diagnose_queries() as report:
        books = list(Book.objects.all())
        for book in books:
            _ = book.author.name  # N+1 on author
        total = len(Book.objects.all())  # queryset_eval  # noqa: F841
        recent = list(Book.objects.filter(published_date__gte="2020-01-01"))  # noqa: F841

    # The line in the synthetic source each issue type is reported against.
    lines = {
        IssueType.N_PLUS_ONE: 2,
        IssueType.QUERYSET_EVAL: 5,
        IssueType.MISSING_INDEX: 6,
    }
    harvested: dict[IssueType, Prescription] = {}
    for rx in report.prescriptions:
        if rx.issue_type in lines and rx.issue_type not in harvested:
            harvested[rx.issue_type] = dataclasses.replace(
                rx,
                callsite=CallSite(
                    filepath=str(source),
                    line_number=lines[rx.issue_type],
                    function_name="book_list",
                ),
            )
    # Positive control: a live run really did produce all three.
    assert set(harvested) == set(lines), sorted(k.value for k in harvested)

    prescriptions = [harvested[kind] for kind in lines]

    fixer = QueryFixer()
    fixes = fixer.generate_fixes(prescriptions)
    assert len(fixes) == 3  # positive control
    diff = fixer.generate_diff(fixes)
    text = (
        "Dry run: showing proposed changes:\n\n"
        + diff
        + f"\n{len(fixes)} fix(es) available. Run with --apply to write changes.\n"
    )
    text.encode("ascii")  # SVG source text must stay ASCII
    _write(SCREENSHOTS / "auto_fix.capture.txt", text, tmp_dir=tmp_path)
