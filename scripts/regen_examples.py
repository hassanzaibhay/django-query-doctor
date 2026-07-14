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
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = REPO_ROOT / "examples" / "outputs"
SCREENSHOTS = REPO_ROOT / "examples" / "screenshots"


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
    (OUTPUTS / "report.json").write_text(
        json.dumps(json.loads(json_text), indent=2, default=str), encoding="utf-8"
    )
    (OUTPUTS / "report.html").write_text(HTMLReporter().render(report), encoding="utf-8")

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

    (OUTPUTS / "query_budget_output.txt").write_text(
        "=" * 60 + "\n"
        "Query Doctor - Query Budget Example\n" + "=" * 60 + "\n\n"
        "@query_budget(max_queries=5)\n"
        "def budget_limited_view():\n"
        "    books = list(Book.objects.all())\n"
        "    for b in books:\n"
        "        _ = b.author.name  # N+1 - exceeds budget\n\n"
        f"Result: {budget_text}\n",
        encoding="utf-8",
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
    (SCREENSHOTS / "console_output.capture.txt").write_text(output, encoding="utf-8")


def test_capture_fix_queries_dry_run(tmp_path: Path) -> None:
    """Capture a real QueryFixer dry-run diff for auto_fix.svg.

    Exactly what fix_queries prints on the dry-run path, including the
    [MANUAL FIX ONLY] tag on the N+1 hunk that --apply refuses to write.
    """
    from query_doctor.fixer import QueryFixer
    from query_doctor.types import CallSite, IssueType, Prescription, Severity

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

    def rx(issue_type: IssueType, line: int, description: str, fix: str) -> Prescription:
        return Prescription(
            issue_type=issue_type,
            severity=Severity.WARNING,
            description=description,
            fix_suggestion=fix,
            callsite=CallSite(filepath=str(source), line_number=line, function_name="book_list"),
        )

    prescriptions = [
        rx(
            IssueType.N_PLUS_ONE,
            2,
            'N+1 detected: 12 queries for table "myapp_author" (field: author)',
            "Add .select_related('author') to your queryset",
        ),
        rx(
            IssueType.QUERYSET_EVAL,
            5,
            "Inefficient queryset evaluation: len(qs)",
            "Use .count() instead of len() to let the database count rows",
        ),
        rx(
            IssueType.MISSING_INDEX,
            6,
            'Missing index: column "published_date" on Book (table "myapp_book") '
            "is used in WHERE/ORDER BY but has no index",
            "Add db_index=True to the 'published_date' field",
        ),
    ]

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
    (SCREENSHOTS / "auto_fix.capture.txt").write_text(text, encoding="utf-8")
